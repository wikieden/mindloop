"""Replanner — failure-driven repair (P4, B3 typed errors → bounded correction).

When a dispatched `SubTask` comes back `FAILED` with a typed `ErrorCode` + a
`RecoveryHint` (B3), the `Replanner` turns that into a **bounded** corrective
`SubTask` sequence — negation-driven replanning (B2R `l3/replanner.py` +
`L3_cognition.md`). It works at the SubTask level (post-compile), reusing the
failed step's node ids (B9) and adjusting params, so no name round-trip is needed.

**Bounded, monotonic, deterministic.** Per (verb, node-ids) target ≤ `max_per_target`
attempts; a global `max_total` budget guards cross-step loops. Past either cap it
**escalates** — stop and ask the user (a `speak`), never an infinite retry. No
network, no LLM (an LLM fallback is an optional future hook); the decision is a
pure function of the typed failure + counters. Safety still applies: the corrective
plan is re-vetted by Phylax upstream before it dispatches.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING

from .execute import RecoveryKind, SubTask

if TYPE_CHECKING:
    from .episteme import SkillCard
    from .execute import StatusUpdate

_log = logging.getLogger("mindloop.replan")

# Recovery kinds that re-issue the same verb with an adjustment param.
_ADJUST_KINDS: frozenset[RecoveryKind] = frozenset(
    {RecoveryKind.POSITION_OFFSET, RecoveryKind.ORIENTATION_RELAX, RecoveryKind.FORCE_ADJUSTMENT}
)


class ReplanAction(str, Enum):
    """What the replanner decided to do about a failure."""

    RETRY = "retry"  # re-issue the same step unchanged
    ADJUST = "adjust"  # re-issue with a typed adjustment (offset/relax/force)
    REROUTE = "reroute"  # re-approach (navigate) then re-issue
    SKIP = "skip"  # drop the step, continue the plan
    ESCALATE = "escalate"  # give up (cap hit / no actionable hint) — stop + speak


@dataclass(frozen=True, slots=True)
class ReplanDecision:
    """The replanner's verdict: an action + corrective subtasks (+ a speak if escalating)."""

    action: ReplanAction
    subtasks: tuple[SubTask, ...] = ()
    speak: str = ""

    @property
    def gives_up(self) -> bool:
        """True if this step is abandoned (escalate, or skip with no corrective)."""
        return self.action == ReplanAction.ESCALATE



def _negated(failed: SubTask) -> tuple[str, ...]:
    """The retry's negation set: everything already carried + this failure.

    ``not:<verb>:<failed id>`` is machine-splittable and the id cites the trace
    row holding the full failure detail (B2R negation-learning parity).
    """
    return (*failed.negation_constraints, f"not:{failed.verb}:{failed.id}")


class Replanner:
    """Maps a typed failure to a bounded corrective subtask sequence (B3 → repair).

    Counters are per-instance and session-scoped; call `reset()` to start a new
    task (the trace keeps the history, the counters do not — B2R semantics). Pass
    the originating `SkillCard` to draw an escalation message from its
    `failure_hints`.
    """

    def __init__(self, *, max_per_target: int = 2, max_total: int = 6) -> None:
        self._max_per_target = max_per_target
        self._max_total = max_total
        self._per: dict[tuple[str, tuple[int, ...]], int] = {}
        self._total = 0

    def reset(self) -> None:
        """Start a new task: clear in-task counters (the trace is untouched)."""
        self._per.clear()
        self._total = 0

    def replan(
        self, failed: SubTask, status: StatusUpdate, *, card: SkillCard | None = None
    ) -> ReplanDecision:
        """Decide the bounded correction for one failed subtask."""
        key = (failed.verb, failed.target_node_ids)
        self._per[key] = self._per.get(key, 0) + 1
        self._total += 1

        if self._total > self._max_total:
            _log.warning("global replan budget (%d) exhausted — escalating", self._max_total)
            return ReplanDecision(ReplanAction.ESCALATE, speak=self._escalate_speak(failed, card))
        if self._per[key] > self._max_per_target:
            _log.warning(
                "per-target replan cap (%d) hit for %s — escalating", self._max_per_target, key
            )
            return ReplanDecision(ReplanAction.ESCALATE, speak=self._escalate_speak(failed, card))

        hint = status.recovery_actions[0] if status.recovery_actions else None
        if hint is None:
            # no actionable adjustment from the body -> hand back to the user
            return ReplanDecision(ReplanAction.ESCALATE, speak=self._escalate_speak(failed, card))

        if hint.kind == RecoveryKind.RETRY:
            return ReplanDecision(ReplanAction.RETRY, (self._fresh(failed),))
        if hint.kind in _ADJUST_KINDS:
            adjusted = self._adjusted(failed, hint.kind, hint.value)
            return ReplanDecision(ReplanAction.ADJUST, (adjusted,))
        if hint.kind == RecoveryKind.REPLAN:
            # re-approach the object, then re-issue the original verb
            return ReplanDecision(
                ReplanAction.REROUTE, (self._navigate(failed), self._fresh(failed))
            )
        if hint.kind == RecoveryKind.SKIP:
            return ReplanDecision(ReplanAction.SKIP)
        return ReplanDecision(ReplanAction.ESCALATE, speak=self._escalate_speak(failed, card))

    # -- corrective subtask builders (reuse node ids, B9) ------------------- #
    def _fresh(self, failed: SubTask) -> SubTask:
        return replace(
            failed, id=self._new_id(failed), negation_constraints=_negated(failed)
        )

    def _adjusted(self, failed: SubTask, kind: RecoveryKind, value: float | None) -> SubTask:
        params = {**failed.params, "recovery": kind.value}
        if value is not None:
            params["recovery_value"] = value
        return replace(
            failed,
            id=self._new_id(failed),
            params=params,
            negation_constraints=_negated(failed),
        )

    def _navigate(self, failed: SubTask) -> SubTask:
        return SubTask(
            id=self._new_id(failed, "nav"),
            verb="navigate",
            target_node_ids=failed.target_node_ids,
        )

    @staticmethod
    def _new_id(failed: SubTask, tag: str = "rp") -> str:
        return f"{failed.id}-{tag}-{uuid.uuid4().hex[:6]}"

    def _escalate_speak(self, failed: SubTask, card: SkillCard | None) -> str:
        if card is not None and card.failure_hints:
            return card.failure_hints[0]
        return f"I tried to {failed.verb} a few times without success — could you help?"
