"""Brain — the cognitive loop binding memory + reasoning (+ optional perception).

`Brain` ties a `tempomem.TempoMem` (the hippocampus) to a `Reasoner` (the
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
from .execute import StatusUpdate, TaskStatus
from .execute import SubTask as _SubTask
from .health import HealthReport
from .interrupt import BargeClassifier, BargeDecision
from .phylax import refusal_speak
from .plan import HandleResult, Plan, compile_commands
from .reason import Answer, Reasoner
from .replan import ReplanAction
from .scene_context import DefaultSceneContextProvider, Focus
from .world_state import WorldState, parse_effect

if TYPE_CHECKING:
    import numpy as np
    from tempomem import Detection, PerceptionAdapter, TempoMem

    from .active_perception import ActivePerception
    from .clarify import Clarifier
    from .execute import CapabilityManifest, ExecutorAdapter, SubTask
    from .interrupt import InterruptSource
    from .phylax import Phylax, SafetyContext
    from .plan import IntentRouter, Planner
    from .preference import PreferenceStore
    from .replan import Replanner
    from .scene_context import SceneContextProvider
    from .trace import TraceStore
    from .voice import Speaker

# D-P build-time constant: reliability buckets below this are disclosed in the
# planner context; healthy skills stay a bare vocabulary word.
_RELIABILITY_DISCLOSE = 0.8


def _verb_vocab(manifest: CapabilityManifest) -> list[str]:
    """The planner-facing verb vocabulary, weak skills annotated inline (D-P)."""
    out: list[str] = []
    for v in sorted(manifest.verbs, key=lambda v: v.name):
        low = {b: r for b, r in v.reliability.items() if r < _RELIABILITY_DISCLOSE}
        if low:
            buckets = ", ".join(f"{b}:{r:.2f}" for b, r in sorted(low.items()))
            out.append(f"{v.name} (reliability {buckets})")
        else:
            out.append(v.name)
    return out


class Brain:
    """Memory + Reasoner cognitive loop.

    `ask` (retrieve → reason) needs only `mem` + `reasoner`. The full S2 loop
    `handle` (route → plan → dispatch, P1) additionally needs a `router`, a
    `planner`, and an `executor` (a `bodylink.MockBody` or a real body); without
    them `handle` raises rather than guessing.
    """

    def __init__(
        self,
        mem: TempoMem,
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
        context_provider: SceneContextProvider | None = None,
        world_state: WorldState | None = None,
        active_perception: ActivePerception | None = None,
        max_tail_replans: int = 1,
        default_speak: str = "OK.",
        interrupts: InterruptSource | None = None,
        barge: BargeClassifier | None = None,
        speaker: Speaker | None = None,
        clarifier: Clarifier | None = None,
        ask_budget: int = 2,
    ) -> None:
        self._mem = mem
        self._reasoner = reasoner
        self._adapter = adapter
        self._budget = max_tokens
        # The read-path seam (dynamic-scene P1): builds the serialized scene context
        # for a Focus + a map version. Default wraps today's query+serialize exactly.
        self._ctx = context_provider or DefaultSceneContextProvider(mem, default_budget=max_tokens)
        # Symbolic effect write-back overlay (dynamic-scene P2): facts the brain
        # knows from completed actions, injected into context so a multi-step task
        # stays grounded without re-perceiving every step.
        self._world = world_state or WorldState()
        # Optional active perception (dynamic-scene P4): re-looks between steps; fused
        # detections can trigger a bounded tail re-plan from fresh context.
        self._perception = active_perception
        self._max_tail_replans = max(0, max_tail_replans)
        # Barge-in (3b, D2/D-E): a non-blocking utterance inbox polled between
        # steps; the classifier decides resume/supersede/correct/abort. The
        # optional speaker voices inline answers and the abort acknowledgement.
        self._interrupts = interrupts
        self._barge = barge
        self._speaker = speaker
        self._barge_n = 0
        # Ask-human seam (3b, D3): a reachable dead-end ESCALATE asks a targeted
        # question instead of giving up; ≤ ask_budget asks per task (reset per
        # task, ratified) and the answer's re-plan is re-vetted by Phylax.
        self._clarifier = clarifier
        self._ask_budget = max(0, ask_budget)
        self._ask_n = 0
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
        stats = self._mem.commit()
        self._bump_map_version()
        return stats

    def ingest(self, detections: list[Detection], *, episode: str | None = None) -> Any:
        """Remember caller-supplied detections (BYO perception), then fuse."""
        self._mem.add_detections(detections, episode=episode)
        stats = self._mem.commit()
        self._bump_map_version()
        return stats

    def _bump_map_version(self) -> None:
        """Advance the context provider's map version after a perception write (P1)."""
        bump = getattr(self._ctx, "bump", None)
        if callable(bump):
            bump()

    @property
    def world(self) -> WorldState:
        """The symbolic world-state overlay (dynamic-scene P2) — facts from actions."""
        return self._world

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
        scene, _ = self._ctx.context(Focus(query=question), k=k, max_tokens=self._budget)
        context = self._assemble_context(scene, dialogue=dialogue)
        return self._reasoner.reason(question, context)

    def _assemble_context(self, scene: str, *, dialogue: str = "") -> str:
        """Stack the recent dialogue (P5), the symbolic world-state (P2), and the
        serialized scene subgraph into one context block."""
        blocks: list[str] = []
        if dialogue:
            blocks.append(f"CONVERSATION (recent turns):\n{dialogue}")
        world = self._world.render()
        if world:
            blocks.append(world)
        blocks.append(scene)
        return "\n\n".join(blocks)

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
        self._session_n += 1
        session = f"s{self._session_n}"
        plan = self._plan_task(instruction, manifest, person, k=k)

        # D-I: a non-fungible binding ambiguity asks a human ONCE before acting
        # (shared per-task ask budget; the folded answer re-plans and then flows
        # through the Phylax gate below like any instruction). Without a
        # clarifier the plan proceeds on the compiler's top-1 binding.
        asks_used = 0
        if plan.ambiguities and self._clarifier is not None and self._ask_budget > 0:
            amb = plan.ambiguities[0]
            options = " or ".join(f"{label} (#{nid})" for nid, label in amb.candidates)
            question = f"Which one do you mean by '{amb.mention}': {options}?"
            answer = self._clarifier.clarify(question)
            asks_used = 1
            self._trace_ask(question, answer, session)
            if answer:
                instruction = f"{instruction} ({answer})"
                plan = self._plan_task(instruction, manifest, person, k=k)

        if self._policy is not None:
            violations = self._policy.check(plan, safety_context)
            if violations:
                # Safety-class block (D4 §9): refuse the whole plan, speak why, and
                # dispatch nothing. The lower must-not overrides the upper want-to.
                blocked = replace(plan, speak=refusal_speak(violations))
                return HandleResult(intent=intent, plan=blocked, violations=violations)

        statuses, escalation = self._dispatch_plan(
            plan,
            instruction=instruction,
            manifest=manifest,
            person=person,
            k=k,
            safety_context=safety_context,
            session=session,
            asks_used=asks_used,
        )
        if escalation is not None:
            plan = replace(plan, speak=escalation)
        return HandleResult(intent=intent, plan=plan, statuses=statuses)

    def _plan_task(
        self, instruction: str, manifest: CapabilityManifest, person: str, *, k: int
    ) -> Plan:
        """Plan a task: LLM verb sequence → compile (D3/B9) → L5 preference overlay.

        Re-runnable mid-execution (dynamic-scene P3/P4): a re-plan re-queries the
        scene context, which now reflects completed-action effects (P2) and any
        fresh perception (P4), so the new plan is grounded in the current world.
        """
        assert self._planner is not None  # guaranteed by handle's guard
        context = self._plan_context(instruction, manifest=manifest, k=k)
        plan = compile_commands(
            self._planner.plan(instruction, context),
            self._mem,
            manifest,
            default_speak=self._default_speak,
        )
        if self._preferences is not None and person:
            plan = self._overlay_preferences(plan, person, manifest)
        return plan

    def _overlay_preferences(self, plan: Plan, person: str, manifest: CapabilityManifest) -> Plan:
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
        self,
        plan: Plan,
        *,
        instruction: str,
        manifest: CapabilityManifest,
        person: str,
        k: int,
        safety_context: SafetyContext | None,
        session: str,
        asks_used: int = 0,
    ) -> tuple[tuple[StatusUpdate, ...], str | None]:
        """Dispatch the plan, with failure repair (P4) + active-perception re-plan (P4-dyn).

        Per step, in order: (1) **active perception** may re-look (`perceive`) — fused
        detections bump the map and, bounded by `max_tail_replans`, trigger a **tail
        re-plan** from fresh context; (2) **idempotent skip** of a step the world-state
        already satisfies (P3); (3) dispatch, and on a typed `FAILED` feed the
        `Replanner` (P4) — an escalation stops the plan with a `speak`.
        """
        if self._replanner is not None:
            self._replanner.reset()  # new task: counters reset, trace untouched

        subs = list(plan.subtasks)
        statuses: list[StatusUpdate] = []
        replans = 0
        # D3: budget resets per task; a D-I binding ask upstream already spent from it
        ask_left = max(0, self._ask_budget - asks_used)
        i = 0
        while i < len(subs):
            # (0) barge-in (3b): poll the interrupt inbox between steps (D-E
            # precision — a step in progress finishes first; mid-step preemption
            # needs the bodylink cancel/pause/resume handshake, deferred to P4).
            if self._interrupts is not None:
                utt = self._interrupts.poll()
                if utt is not None:
                    act, payload = self._handle_barge(
                        utt,
                        instruction,
                        manifest,
                        person,
                        k=k,
                        safety_context=safety_context,
                        session=session,
                    )
                    if act == "abort":
                        return tuple(statuses), payload
                    if act == "replace":
                        new_subs, instruction = payload
                        subs = subs[:i] + new_subs
                        continue
                    # "resume": answered inline — carry on with the current step
            sub = subs[i]

            # (1) active perception (dynamic-scene P4) — re-look between steps
            if self._perception is not None and replans < self._max_tail_replans:
                last = statuses[-1] if statuses else None
                dets = self._perception.perceive(step_index=i, last_status=last)
                if dets:
                    self.ingest(dets)  # fuse → map version bump
                    replans += 1
                    new_plan = self._plan_task(instruction, manifest, person, k=k)
                    if self._policy is not None:
                        viol = self._policy.check(new_plan, safety_context)
                        if viol:
                            return tuple(statuses), refusal_speak(viol)
                    # splice the fresh tail in place of the remaining steps; already-done
                    # steps are dropped by the idempotent skip below
                    subs = subs[:i] + list(new_plan.subtasks)
                    continue

            # (2) idempotent skip (dynamic-scene P3)
            if self._already_satisfied(sub):
                st = self._skipped(sub)
                self._record(sub, st, session)
                statuses.append(st)
                i += 1
                continue

            # (3) dispatch + typed-failure repair (P4)
            st = self._drain(sub)
            self._record(sub, st, session)
            if st.status.value == "failed" and self._replanner is not None:
                st, escalation = self._repair(sub, st, safety_context, session)
                if escalation is not None:
                    # 3b (D3): a dead-end ESCALATE asks a human before giving up —
                    # bounded by the per-task ask budget, answer re-vetted below.
                    if self._clarifier is not None and ask_left > 0:
                        ask_left -= 1
                        question = f"I'm stuck: {escalation} What should I do?"
                        answer = self._clarifier.clarify(question)
                        self._trace_ask(question, answer, session)
                        if answer:
                            goal = f"{instruction} ({answer})"
                            new_plan = self._plan_task(goal, manifest, person, k=k)
                            if self._policy is not None:
                                viol = self._policy.check(new_plan, safety_context)
                                if viol:
                                    # the answer is an instruction: a blocked one
                                    # refuses, it never sneaks past the gate
                                    statuses.append(st)
                                    return tuple(statuses), refusal_speak(viol)
                            statuses.append(st)
                            instruction = goal
                            subs = subs[:i] + list(new_plan.subtasks)
                            continue
                    statuses.append(st)
                    return tuple(statuses), escalation  # safety-class stop: end plan
            statuses.append(st)
            i += 1
        return tuple(statuses), None

    def _handle_barge(
        self,
        utterance: str,
        instruction: str,
        manifest: CapabilityManifest,
        person: str,
        *,
        k: int,
        safety_context: SafetyContext | None,
        session: str,
    ) -> tuple[str, Any]:
        """Act on a mid-task utterance (3b): returns one of
        ``("abort", speak)`` / ``("resume", None)`` / ``("replace", (subs, goal))``.

        A barge-triggered re-plan (supersede/correction) is **re-vetted by
        Phylax** before it replaces anything — a barge-in must not smuggle a
        blocked action past the gate. Every decision is traced (verb
        ``barge_in``) so interrupt handling stays auditable.
        """
        clf = self._barge or (BargeClassifier(self._router) if self._router is not None else None)
        if clf is None:  # no router to classify with: ignore rather than guess
            return ("resume", None)
        decision = clf.classify(utterance)
        self._trace_barge(decision, session)
        if decision.kind == "abort":
            speak = "Okay — stopping."
            if self._speaker is not None:
                self._speaker.say(speak)
            return ("abort", speak)
        if decision.kind == "answer_resume":
            ans = self.ask(utterance, k=k)
            if self._speaker is not None:
                self._speaker.say(ans.text)
            return ("resume", None)
        # supersede: the utterance IS the new goal; correction: same goal + fix
        goal = utterance if decision.kind == "supersede" else f"{instruction} ({utterance})"
        new_plan = self._plan_task(goal, manifest, person, k=k)
        if self._policy is not None:
            viol = self._policy.check(new_plan, safety_context)
            if viol:
                return ("abort", refusal_speak(viol))
        return ("replace", (list(new_plan.subtasks), goal))

    def _trace_barge(self, decision: BargeDecision, session: str) -> None:
        if self._trace is None:
            return
        self._barge_n += 1
        sub = _SubTask(
            id=f"barge-{self._barge_n}",
            verb="barge_in",
            params={"kind": decision.kind, "utterance": decision.utterance},
        )
        st = StatusUpdate(
            "",
            sub.id,
            TaskStatus.SUCCESS,
            progress=1.0,
            message=f"barge_in:{decision.kind} {decision.utterance!r}",
        )
        self._trace.log_attempt(sub, st, session_id=session)

    def _trace_ask(self, question: str, answer: str | None, session: str) -> None:
        if self._trace is None:
            return
        self._ask_n += 1
        sub = _SubTask(
            id=f"ask-{self._ask_n}",
            verb="ask_human",
            params={"question": question, "answer": answer or ""},
        )
        st = StatusUpdate(
            "",
            sub.id,
            TaskStatus.SUCCESS if answer else TaskStatus.FAILED,
            progress=1.0,
            message=f"ask_human -> {answer!r}",
        )
        self._trace.log_attempt(sub, st, session_id=session)

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
        # Effect write-back (dynamic-scene P2): a confirmed success updates the
        # symbolic world-state, so the next step's context reflects this action's
        # result without re-perceiving.
        if st.status.value == "success":
            self._world.apply(sub.effects)

    def _already_satisfied(self, sub: SubTask) -> bool:
        """True if every one of `sub`'s effects already holds in the world-state (P3).

        Open-world + conservative: a step with no effects, or any effect we can't
        parse, is **not** skippable (we only skip when we can positively confirm the
        outcome is already in place). Prevents redoing completed work after a replan.
        """
        if not sub.effects:
            return False
        parsed = [parse_effect(s) for s in sub.effects]
        if any(e is None for e in parsed):
            return False
        return all(self._world.get(e.key) == e.value for e in parsed if e is not None)

    def _skipped(self, sub: SubTask) -> StatusUpdate:
        """A synthetic terminal SUCCESS for an idempotently-skipped subtask."""
        return StatusUpdate(
            task_id="",
            subtask_id=sub.id,
            status=TaskStatus.SUCCESS,
            progress=1.0,
            touched_node_ids=sub.target_node_ids,
            message="already satisfied (idempotent skip)",
        )

    def _plan_context(self, instruction: str, *, manifest: CapabilityManifest, k: int) -> str:
        """Build the planner's context: the relevant scene subgraph + the verb
        vocabulary the body supports (so the LLM only plans dispatchable verbs).

        D-P: a verb whose scorecard reliability is below the disclosure bar is
        annotated inline ("grasp (reliability fragile:0.55)") so the LLM can
        route around a weak skill or pre-disclose — advisory only, never safety.
        """
        scene, _ = self._ctx.context(Focus(query=instruction), k=k, max_tokens=self._budget)
        grounded = self._assemble_context(scene)
        return f"Available verbs: {', '.join(_verb_vocab(manifest))}\n\nSCENE:\n{grounded}"

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
