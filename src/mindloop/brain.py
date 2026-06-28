"""Brain — the cognitive loop binding memory + reasoning (+ optional perception).

`Brain` ties a `tempomem.SpatialMemory` (the hippocampus) to a `Reasoner` (the
cortex), with an optional `tempomem.PerceptionAdapter` (the eyes, from
`worldsense`). The tick is: perceive → remember (observe/ingest),
then on demand retrieve → reason (ask). See docs/cosmos3-tempomem-llm-brain.md.

v0 is single-threaded; serialize all access (the core store is one sqlite
connection). Active perception (LLM → re-look) is future work.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .dialogue import Conversation
from .episteme import manifest_param_keys
from .errors import BrainError
from .health import HealthReport
from .phylax import refusal_speak
from .plan import HandleResult, Plan, compile_commands
from .reason import Answer, Reasoner
from .replan import ReplanAction

if TYPE_CHECKING:
    import numpy as np
    from tempomem import Detection, PerceptionAdapter, SpatialMemory

    from .execute import CapabilityManifest, ExecutorAdapter, StatusUpdate, SubTask
    from .phylax import Phylax, SafetyContext
    from .plan import IntentRouter, Planner
    from .preference import PreferenceStore
    from .replan import Replanner
    from .trace import TraceStore


class Brain:
    """Memory + Reasoner cognitive loop.

    `ask` (retrieve → reason) needs only `mem` + `reasoner`. The full S2 loop
    `handle` (route → plan → dispatch, P1) additionally needs a `router`, a
    `planner`, and an `executor` (a `bodylink.MockBody` or a real body); without
    them `handle` raises rather than guessing.
    """

    def __init__(
        self,
        mem: SpatialMemory,
        reasoner: Reasoner,
        *,
        adapter: PerceptionAdapter | None = None,
        max_tokens: int = 1500,
        router: IntentRouter | None = None,
        planner: Planner | None = None,
        executor: ExecutorAdapter | None = None,
        policy: Phylax | None = None,
        replanner: Replanner | None = None,
        trace: TraceStore | None = None,
        preferences: PreferenceStore | None = None,
        default_speak: str = "OK.",
    ) -> None:
        self._mem = mem
        self._reasoner = reasoner
        self._adapter = adapter
        self._budget = max_tokens
        self._router = router
        self._planner = planner
        self._executor = executor
        # Optional brain-side semantic safety tier (P3, D4). When wired, every
        # task plan is vetted before dispatch; a violation blocks the whole plan
        # (stop + speak, no reroute). None ⇒ no gate (dispatch as in P1/P2).
        self._policy = policy
        # Optional failure-driven repair (P4). `replanner` turns a typed FAILED
        # StatusUpdate (B3) into a bounded corrective sequence; `trace` logs every
        # attempt/failure (L4 episodic, citing node ids). None ⇒ dispatch once.
        self._replanner = replanner
        self._trace = trace
        # Optional L5 per-person preference store (P5/D2). When wired, a person's
        # preferences overlay a compiled task plan's params (manifest-gated).
        self._preferences = preferences
        self._session_n = 0
        # Floor utterance when a task plan dispatches but the planner LLM omitted
        # a `speak` line — guarantees user feedback even with a weak instruction
        # follower. Override to localize (e.g. "好的。").
        self._default_speak = default_speak

    def observe(
        self,
        rgb: np.ndarray,
        depth: np.ndarray,
        pose: np.ndarray,
        *,
        adapter: PerceptionAdapter | None = None,
        episode: str | None = None,
    ) -> Any:
        """Perceive → remember: run a posed frame through perception, then fuse.

        Needs a `PerceptionAdapter` (here or at construction) — perception lives
        in the `worldsense` companion repo. Returns the commit stats.
        """
        self._mem.add_frame(rgb, depth, pose, adapter=adapter or self._adapter, episode=episode)
        return self._mem.commit()

    def ingest(self, detections: list[Detection], *, episode: str | None = None) -> Any:
        """Remember caller-supplied detections (BYO perception), then fuse."""
        self._mem.add_detections(detections, episode=episode)
        return self._mem.commit()

    def ask(self, question: str, *, k: int = 64, dialogue: str = "") -> Answer:
        """Retrieve a query-relevant subgraph → reason → answer.

        Retrieves the top-`k` nodes for `question` and serializes that subgraph —
        the hits, their 1-hop relation neighbours, and the hierarchy ancestors of
        both — within the token budget, rather than dumping the whole scene
        truncated, so the relevant objects survive a tight budget. Falls back to
        the whole scene when nothing matches. `k` is deliberately generous so the
        token budget (not `k`) is the binding limit on a normal scene; an
        enumerative query over more than `k` same-label objects is capped at `k`.

        `dialogue` (P5) is recent conversation history; when given it is prepended
        to the reasoner context so a follow-up resolves against prior turns.
        """
        hits = self._mem.query(question, k=k)
        node_ids = {n.id for n in hits.nodes}
        if node_ids:
            context = self._mem.serialize(
                format="prompt", node_ids=node_ids, max_tokens=self._budget
            )
        else:
            context = self._mem.serialize(format="prompt", max_tokens=self._budget)
        if dialogue:
            context = f"CONVERSATION (recent turns):\n{dialogue}\n\n{context}"
        return self._reasoner.reason(question, context)

    def converse(
        self,
        instruction: str,
        conversation: Conversation | None = None,
        *,
        k: int = 64,
        person: str = "",
        safety_context: SafetyContext | None = None,
    ) -> HandleResult:
        """Run one conversational turn (P5): `handle` with dialogue history, then record.

        Threads `conversation`'s recent turns into `handle` (so question/chat turns
        are dialogue-grounded) and appends the resulting turn. Pass a `Conversation`
        you keep across turns; a fresh one is created (and the turn recorded into it)
        if omitted.
        """
        conv = conversation if conversation is not None else Conversation()
        result = self.handle(
            instruction,
            k=k,
            person=person,
            safety_context=safety_context,
            dialogue=conv.history_text(),
        )
        conv.add(instruction, result)
        return result

    def handle(
        self,
        instruction: str,
        *,
        k: int = 64,
        person: str = "",
        safety_context: SafetyContext | None = None,
        dialogue: str = "",
    ) -> HandleResult:
        """The full S2 loop (P1+P3+P4+P5): route an instruction → answer or plan + dispatch.

        `question`/`chat` route to `ask` (retrieve → reason → cited `Answer`). A
        `task` is planned into a verb `Command` sequence (B2R two-stage format),
        compiled into node-bound `SubTask`s gated by the body's manifest (D3/B9).
        If a `policy` (Phylax) is wired, the compiled plan is then vetted against
        `safety_context` **before** dispatch (P3): any violation **blocks the whole
        plan** — stop + speak, no reroute, no retry (D4 §9) — and the result
        carries the `violations` with nothing dispatched. A cleared plan is
        dispatched, returning each subtask's terminal `StatusUpdate`. Raises
        `BrainError` if the routing/planning collaborators are not configured.
        """
        if self._router is None or self._planner is None:
            raise BrainError("Brain.handle needs router= and planner= (see Brain.__init__)")

        intent = self._router.classify(instruction)
        if intent in ("question", "chat"):
            return HandleResult(intent=intent, answer=self.ask(instruction, k=k, dialogue=dialogue))

        if self._executor is None:
            raise BrainError("Brain.handle with a task intent needs executor= (a body)")
        manifest = self._executor.capabilities()
        context = self._plan_context(instruction, manifest_verbs=sorted(manifest.verb_names()), k=k)
        plan = compile_commands(
            self._planner.plan(instruction, context),
            self._mem,
            manifest,
            default_speak=self._default_speak,
        )

        if self._preferences is not None and person:
            plan = self._overlay_preferences(plan, person, manifest)

        if self._policy is not None:
            violations = self._policy.check(plan, safety_context)
            if violations:
                # Safety-class block (D4 §9): refuse the whole plan, speak why, and
                # dispatch nothing. The lower must-not overrides the upper want-to.
                blocked = replace(plan, speak=refusal_speak(violations))
                return HandleResult(intent=intent, plan=blocked, violations=violations)

        statuses, escalation = self._dispatch_plan(plan, safety_context)
        if escalation is not None:
            plan = replace(plan, speak=escalation)
        return HandleResult(intent=intent, plan=plan, statuses=statuses)

    def _overlay_preferences(
        self, plan: Plan, person: str, manifest: CapabilityManifest
    ) -> Plan:
        """Overlay a person's L5 preferences onto each subtask's params (P5).

        Preferences win over card/rule defaults, but only for the params the body
        declares for that verb (manifest-gated — a preference can't inject an
        unknown key). Returns the plan unchanged if nothing applies.
        """
        assert self._preferences is not None
        prefs = self._preferences.all(person)
        if not prefs:
            return plan
        new_subs: list[SubTask] = []
        changed = False
        for st in plan.subtasks:
            known = manifest_param_keys(manifest, st.verb)
            overlay = {k: v for k, v in prefs.items() if k in known}
            if overlay:
                new_subs.append(replace(st, params={**st.params, **overlay}))
                changed = True
            else:
                new_subs.append(st)
        return replace(plan, subtasks=tuple(new_subs)) if changed else plan

    def _dispatch_plan(
        self, plan: Plan, safety_context: SafetyContext | None
    ) -> tuple[tuple[StatusUpdate, ...], str | None]:
        """Dispatch each subtask, repairing failures via the replanner (P4).

        Without a `replanner`, this is the P1-P3 behavior (dispatch each subtask
        once). With one, a `FAILED` terminal is fed to `Replanner.replan` and the
        bounded corrective sequence is dispatched in its place; an escalation stops
        the plan and returns a `speak`. Every attempt is logged to the trace.
        """
        if self._replanner is not None:
            self._replanner.reset()  # new task: counters reset, trace untouched
        self._session_n += 1
        session = f"s{self._session_n}"

        statuses: list[StatusUpdate] = []
        for sub in plan.subtasks:
            st = self._drain(sub)
            self._record(sub, st, session)
            if st.status.value == "failed" and self._replanner is not None:
                st, escalation = self._repair(sub, st, safety_context, session)
                if escalation is not None:
                    statuses.append(st)
                    return tuple(statuses), escalation  # safety-class stop: end plan
            statuses.append(st)
        return tuple(statuses), None

    def _repair(
        self, sub: SubTask, st: StatusUpdate, safety_context: SafetyContext | None, session: str
    ) -> tuple[StatusUpdate, str | None]:
        """Bounded repair loop for one failed subtask. Returns (terminal, escalation)."""
        assert self._replanner is not None
        while st.status.value == "failed":
            decision = self._replanner.replan(sub, st)
            if decision.action == ReplanAction.SKIP:
                return st, None  # drop this step, keep the plan going
            if decision.gives_up:
                return st, decision.speak  # escalate: stop + speak
            # Safety still applies to a corrective plan (P3): re-vet before acting.
            if self._policy is not None:
                viol = self._policy.check(Plan(subtasks=decision.subtasks), safety_context)
                if viol:
                    return st, refusal_speak(viol)
            for cs in decision.subtasks:
                st = self._drain(cs)
                self._record(cs, st, session)
                sub = cs  # the retried step keys the next replan
        return st, None  # recovered

    def _record(self, sub: SubTask, st: StatusUpdate, session: str) -> None:
        if self._trace is not None:
            self._trace.log_attempt(sub, st, session_id=session)

    def _plan_context(self, instruction: str, *, manifest_verbs: list[str], k: int) -> str:
        """Build the planner's context: the relevant scene subgraph + the verb
        vocabulary the body supports (so the LLM only plans dispatchable verbs)."""
        hits = self._mem.query(instruction, k=k)
        node_ids = {n.id for n in hits.nodes}
        scene = (
            self._mem.serialize(format="prompt", node_ids=node_ids, max_tokens=self._budget)
            if node_ids
            else self._mem.serialize(format="prompt", max_tokens=self._budget)
        )
        return f"Available verbs: {', '.join(manifest_verbs)}\n\nSCENE:\n{scene}"

    def _drain(self, subtask: Any) -> StatusUpdate:
        """Consume a dispatch `StatusUpdate` stream to its terminal element."""
        last: StatusUpdate | None = None
        for update in self._executor.dispatch(subtask):  # type: ignore[union-attr]
            last = update
        if last is None:
            raise BrainError(f"executor yielded no StatusUpdate for subtask {subtask.id!r}")
        return last

    def health(self) -> HealthReport:
        """Report brain readiness (B5), mirroring the body's L3 init checklist.

        Reasoner (their `llm_model`) and memory (their `world_model`) are wired
        at construction; the skill library (their `task_library`) lands in P2, so
        `skill_library_ready` is left `None` for now.
        """
        return HealthReport(
            reasoner_ready=self._reasoner is not None,
            memory_ready=self._mem is not None,
        )
