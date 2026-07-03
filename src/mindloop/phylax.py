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
    from collections.abc import Mapping

    from .episteme import SkillCard
    from .menu import MenuKB
    from .plan import Plan

_log = logging.getLogger("mindloop.phylax")

# Permission tiers (B2R §8): an adult (parent) holds full rights; stranger is the
# conservative default — when in doubt, assume the least privilege.
Role = Literal["adult", "child", "guest", "stranger"]

# Verbs that move the base — the ones a human-proximity speed cap applies to.
_LOCOMOTION: frozenset[str] = frozenset({"navigate", "climb_stair"})

# Verbs whose target/first arg is a *region* — the ones region-access gates read
# (Q6 / D-A). `location`-named params are region-positions on any verb.
_REGION_TARGET_VERBS: frozenset[str] = frozenset(
    {"navigate", "present", "sweep", "vacuum", "mop", "warn_wet_floor"}
)

# Verbs that hand an item to a person — the allergen invariant applies (D-K/D-L).
_SERVE_VERBS: frozenset[str] = frozenset({"offer", "deliver"})


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
    # D-A dual identity: the robot's *active service role* for this task
    # ("cleaner"/"host"/"guide"/None). Orthogonal to `role` (the requester);
    # None skips the service-region gate (backward compat).
    robot_service: str | None = None
    # D-K/D-L allergen state of the person being served. `allergy_status_known`
    # is False until the per-role SkillCard procedure (or install-time data)
    # establishes it — fail-closed: serve-class verbs are blocked while unknown.
    allergies: frozenset[str] = field(default_factory=frozenset)
    allergy_status_known: bool = False


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
    # D1 — param-scoped permission: verb -> param name -> values that need
    # role=adult (e.g. operate_appliance/appliance_type/{stove}); other values
    # of the same verb stay open. Read from `params` then `named_params`.
    adult_only_verb_params: Mapping[str, Mapping[str, frozenset[str]]] = field(default_factory=dict)
    # D-A — region label -> the robot_service values allowed to act there
    # (empty set = no service may). Only consulted when the context carries an
    # active `robot_service`.
    service_permitted_regions: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # Q6 — requester-side region access for guest/stranger: default-allow over
    # *registered* regions with an explicit denylist; a region absent from
    # `known_regions` is refused (unknown ≠ allowed). Empty `known_regions`
    # disables the whole check (feature off / backward compat).
    known_regions: frozenset[str] = field(default_factory=frozenset)
    guest_blocked_regions: frozenset[str] = field(default_factory=frozenset)
    # D-K — the vetted recipe KB; None disables the allergen invariant.
    menu: MenuKB | None = None


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
            # D1 — param-scoped adult gate: only the restricted values of a
            # (verb, param) need role=adult; sibling values stay open.
            for pname, restricted in p.adult_only_verb_params.get(verb, {}).items():
                value = st.params.get(pname, st.named_params.get(pname))
                if value in restricted and ctx.role != "adult":
                    out.append(
                        Violation(
                            rule="permission.adult_only_param",
                            severity=Severity.HIGH,
                            message=(
                                f"{verb!r} with {pname}={value!r} requires role=adult, "
                                f"got {ctx.role!r}"
                            ),
                            subtask_id=st.id,
                            speak="I can't do that — it needs an adult to ask.",
                        )
                    )
            # region-positions this subtask acts on (Q6 / D-A): an explicit
            # `location` param, plus the target of region-targeting verbs
            regions = [r for r in (st.named_params.get("location"),) if r]
            if verb in _REGION_TARGET_VERBS and st.named_params.get("target"):
                regions.append(st.named_params["target"])
            for region in regions:
                # D-A — active service role vs region grant (grant ∩ need, D-O)
                if (
                    ctx.robot_service is not None
                    and region in p.service_permitted_regions
                    and ctx.robot_service not in p.service_permitted_regions[region]
                ):
                    out.append(
                        Violation(
                            rule="service.region_access",
                            severity=Severity.HIGH,
                            message=(
                                f"service {ctx.robot_service!r} may not act in region {region!r}"
                            ),
                            subtask_id=st.id,
                            speak="That area isn't part of my current duties.",
                        )
                    )
                # Q6 — guest/stranger: default-allow over registered regions,
                # explicit denylist, unknown region refused (never a free pass)
                if p.known_regions and ctx.role in ("guest", "stranger"):
                    if region in p.guest_blocked_regions:
                        out.append(
                            Violation(
                                rule="region.guest_blocked",
                                severity=Severity.HIGH,
                                message=f"region {region!r} is private (guest denylist)",
                                subtask_id=st.id,
                                speak="That area is private — I can't take you there.",
                            )
                        )
                    elif region not in p.known_regions:
                        out.append(
                            Violation(
                                rule="region.unknown",
                                severity=Severity.HIGH,
                                message=f"region {region!r} was never registered at install",
                                subtask_id=st.id,
                                speak="I don't know that area, so I won't go there.",
                            )
                        )
            # D-K / D-L — allergen invariant on serve-class verbs (fail-closed):
            # unknown allergy status or an unvetted/unknown recipe never serves.
            if p.menu is not None and verb in _SERVE_VERBS:
                item = st.named_params.get("item", "")
                if not ctx.allergy_status_known:
                    out.append(
                        Violation(
                            rule="allergy.status_unknown",
                            severity=Severity.HIGH,
                            message=f"serving {item!r} before allergy status was established",
                            subtask_id=st.id,
                            speak="Before I serve anything — any allergies I should know about?",
                        )
                    )
                else:
                    allergens = p.menu.allergens(item, trusted=p.trusted_provenances)
                    if allergens is None and ctx.allergies:
                        out.append(
                            Violation(
                                rule="allergy.unknown_recipe",
                                severity=Severity.HIGH,
                                message=(
                                    f"recipe for {item!r} is unknown/unvetted and the "
                                    f"guest has allergies {sorted(ctx.allergies)}"
                                ),
                                subtask_id=st.id,
                                speak="I'm not sure what's in that, so I won't risk it.",
                            )
                        )
                    elif allergens and allergens & ctx.allergies:
                        hit = sorted(allergens & ctx.allergies)
                        out.append(
                            Violation(
                                rule="allergy.blocked",
                                severity=Severity.CRITICAL,
                                message=f"{item!r} contains {hit} — guest is allergic",
                                subtask_id=st.id,
                                speak="That contains something you're allergic to — "
                                "let me offer an alternative.",
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
