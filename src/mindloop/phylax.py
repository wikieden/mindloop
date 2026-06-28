"""Phylax — the brain-side semantic safety tier (P3, D4 top tier).

D4's guardian (Phylax) is three tiers: a **semantic** tier here in the brain, a
symbolic-BT tier in `bodylink`, and a reflex tier in firmware. This module is the
**semantic** tier only — the portable, brain-side policy gate that vets a compiled
`Plan` *before* it is dispatched. The other two tiers are deferred.

It ports Brain2Robot's `safety_architecture.md` (§2 L3 hard-constraints, §8
permissions, §9 arbitration). The governing principle (§9) is **monotonic
tightening**: *an upper layer's "want-to" never overrides a lower layer's
"must-not"*. So the gate only ever **subtracts** — it blocks, it never reroutes or
retries. A safety-class block is terminal: **stop + speak**, no "try another way".

Checks (declarative `Policy`, evaluated against a `SafetyContext`):

  * **permission** — `adult_only_verbs` may be initiated only by `role="adult"`
    (knives, power tools); everyone else is refused (§8 permission tiers).
  * **supervision** — `supervised_only_verbs` (fire / high-temp appliances) need
    a supervising adult present (§2).
  * **forbidden zone** — a subtask targeting a `forbidden_node_id` is refused.
  * **human-proximity speed cap** — within 1 m of a person, a locomotion verb
    carrying a speed above `max_speed_mps_near_human` is refused (§2 / §8).
  * **untrusted skill card** — a `SkillCard` carrying `safety:` annotations from
    an untrusted `provenance` is refused before it is honored (`vet_card`).

The gate is **opt-in**: a `Brain` with no `policy` dispatches as before. Wire a
`Phylax` to enforce these. Stdlib-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .episteme import SkillCard
    from .plan import Plan

_log = logging.getLogger("mindloop.phylax")

# Permission tiers (B2R §8): an adult (parent) holds full rights; stranger is the
# conservative default — when in doubt, assume the least privilege.
Role = Literal["adult", "child", "guest", "stranger"]

# Verbs that move the base — the ones a human-proximity speed cap applies to.
_LOCOMOTION: frozenset[str] = frozenset({"navigate", "climb_stair"})


class Severity(str, Enum):
    """How a violation is handled. Both block dispatch; `CRITICAL` is reserved for
    a hard safety-class stop, `HIGH` for a permission/zone refusal."""

    CRITICAL = "critical"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Violation:
    """One reason a plan was refused — a blocked subtask + a user-facing message."""

    rule: str
    severity: Severity
    message: str
    subtask_id: str = ""
    speak: str = ""


@dataclass(frozen=True, slots=True)
class SafetyContext:
    """The situation a plan is evaluated against (from the identity/perception layer).

    Conservative defaults (B2R §8 "unknown → conservative"): an unidentified
    `stranger`, no supervising adult, and — unless perception says otherwise — no
    human assumed within reach (the speed cap only bites when a person *is* near).
    """

    role: Role = "stranger"
    humans_within_1m: bool = False
    supervised: bool = False


@dataclass(frozen=True, slots=True)
class Policy:
    """Declarative safety policy — the hard constraints the gate enforces.

    All fields are data, authored per deployment. Empty sets disable a check. The
    speed cap only applies when `SafetyContext.humans_within_1m` is true and a
    locomotion subtask carries a `speed_param` value above the cap.
    """

    adult_only_verbs: frozenset[str] = field(default_factory=frozenset)
    supervised_only_verbs: frozenset[str] = field(default_factory=frozenset)
    forbidden_node_ids: frozenset[int] = field(default_factory=frozenset)
    max_speed_mps_near_human: float = 0.3
    speed_param: str = "speed_mps"
    # A skill card carrying `safety:` annotations is honored only if its
    # `provenance` is in this set (signed / reviewed). Default trusts builtins.
    trusted_provenances: frozenset[str] = field(default_factory=lambda: frozenset({"builtin"}))


class Phylax:
    """The semantic safety gate: vet a `Plan` (and skill cards) against a `Policy`.

    `check` returns every `Violation` it finds (empty ⇒ the plan is cleared to
    dispatch). The caller blocks the **whole** plan on any violation — a partial
    safety pass is not a thing (§9: no rerouting around a must-not).
    """

    def __init__(self, policy: Policy | None = None) -> None:
        self._policy = policy or Policy()

    @property
    def policy(self) -> Policy:
        return self._policy

    def check(self, plan: Plan, context: SafetyContext | None = None) -> tuple[Violation, ...]:
        """Vet a compiled plan; return all violations (empty ⇒ cleared)."""
        ctx = context or SafetyContext()
        p = self._policy
        out: list[Violation] = []

        for st in plan.subtasks:
            verb = st.verb
            if verb in p.adult_only_verbs and ctx.role != "adult":
                out.append(
                    Violation(
                        rule="permission.adult_only",
                        severity=Severity.HIGH,
                        message=f"verb {verb!r} requires role=adult, got {ctx.role!r}",
                        subtask_id=st.id,
                        speak="I can't do that — it needs an adult to ask.",
                    )
                )
            if verb in p.supervised_only_verbs and not ctx.supervised:
                out.append(
                    Violation(
                        rule="supervision.required",
                        severity=Severity.HIGH,
                        message=f"verb {verb!r} needs a supervising adult present",
                        subtask_id=st.id,
                        speak="I won't do that unsupervised — please stay nearby.",
                    )
                )
            forbidden = tuple(n for n in st.target_node_ids if n in p.forbidden_node_ids)
            if forbidden:
                out.append(
                    Violation(
                        rule="zone.forbidden",
                        severity=Severity.HIGH,
                        message=f"verb {verb!r} targets forbidden node(s) {forbidden}",
                        subtask_id=st.id,
                        speak="That area is off-limits, so I'll stop.",
                    )
                )
            if ctx.humans_within_1m and verb in _LOCOMOTION:
                speed = _as_float(st.params.get(p.speed_param))
                if speed is not None and speed > p.max_speed_mps_near_human:
                    out.append(
                        Violation(
                            rule="proximity.speed_cap",
                            severity=Severity.CRITICAL,
                            message=(
                                f"{verb!r} at {speed} m/s exceeds "
                                f"{p.max_speed_mps_near_human} m/s near a person"
                            ),
                            subtask_id=st.id,
                            speak="Someone's close, so I'll slow down and stop.",
                        )
                    )
        return tuple(out)

    def vet_card(self, card: SkillCard) -> bool:
        """True if a skill card may be honored. A card carrying `safety:` from an
        untrusted `provenance` is refused (signature/review gate, P3)."""
        if card.safety and card.provenance not in self._policy.trusted_provenances:
            _log.warning(
                "refused skill card %r: safety annotations from untrusted provenance %r",
                card.id,
                card.provenance,
            )
            return False
        return True


def refusal_speak(violations: tuple[Violation, ...]) -> str:
    """A single user-facing utterance for a blocked plan (the first violation's)."""
    for v in violations:
        if v.speak:
            return v.speak
    return "I can't do that safely, so I've stopped."


def _as_float(value: object) -> float | None:
    """Coerce a param value to float, or None if it isn't numeric."""
    if isinstance(value, (int, float)):
        return float(value)
    return None
