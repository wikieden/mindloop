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

from .errors import BrainError
from .health import HealthReport
from .phylax import refusal_speak
from .plan import HandleResult, compile_commands
from .reason import Answer, Reasoner

if TYPE_CHECKING:
    import numpy as np
    from tempomem import Detection, PerceptionAdapter, SpatialMemory

    from .execute import ExecutorAdapter, StatusUpdate
    from .phylax import Phylax, SafetyContext
    from .plan import IntentRouter, Planner


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

    def ask(self, question: str, *, k: int = 64) -> Answer:
        """Retrieve a query-relevant subgraph → reason → answer.

        Retrieves the top-`k` nodes for `question` and serializes that subgraph —
        the hits, their 1-hop relation neighbours, and the hierarchy ancestors of
        both — within the token budget, rather than dumping the whole scene
        truncated, so the relevant objects survive a tight budget. Falls back to
        the whole scene when nothing matches. `k` is deliberately generous so the
        token budget (not `k`) is the binding limit on a normal scene; an
        enumerative query over more than `k` same-label objects is capped at `k`.
        """
        hits = self._mem.query(question, k=k)
        node_ids = {n.id for n in hits.nodes}
        if node_ids:
            context = self._mem.serialize(
                format="prompt", node_ids=node_ids, max_tokens=self._budget
            )
        else:
            context = self._mem.serialize(format="prompt", max_tokens=self._budget)
        return self._reasoner.reason(question, context)

    def handle(
        self,
        instruction: str,
        *,
        k: int = 64,
        safety_context: SafetyContext | None = None,
    ) -> HandleResult:
        """The full S2 loop (P1+P3): route an instruction → answer or plan + dispatch.

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
            return HandleResult(intent=intent, answer=self.ask(instruction, k=k))

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

        if self._policy is not None:
            violations = self._policy.check(plan, safety_context)
            if violations:
                # Safety-class block (D4 §9): refuse the whole plan, speak why, and
                # dispatch nothing. The lower must-not overrides the upper want-to.
                blocked = replace(plan, speak=refusal_speak(violations))
                return HandleResult(intent=intent, plan=blocked, violations=violations)

        statuses = tuple(self._drain(st) for st in plan.subtasks)
        return HandleResult(intent=intent, plan=plan, statuses=statuses)

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
