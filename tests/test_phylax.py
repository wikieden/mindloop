"""P3 — Phylax semantic safety tier (network-free). Ports B2R safety_architecture."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, SpatialMemory

from mindloop import (
    Brain,
    Command,
    Phylax,
    Policy,
    SafetyContext,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    SkillCard,
    SkillCardPlanner,
    SkillLibrary,
    SubTask,
    TaskStatus,
)
from mindloop.plan import Plan

DIM = 16


def _st(verb: str, *, ids: tuple[int, ...] = (), **params: object) -> SubTask:
    return SubTask(id=f"s-{verb}", verb=verb, target_node_ids=ids, params=dict(params))


# --------------------------------------------------------------------------- #
# unit: the gate (Phylax.check)
# --------------------------------------------------------------------------- #
def test_adult_only_verb_blocked_for_non_adult() -> None:
    phylax = Phylax(Policy(adult_only_verbs=frozenset({"grasp"})))
    plan = Plan(subtasks=(_st("grasp", ids=(1,)),))
    # a child initiating a blade-class op -> refused (B2R §8 permission tiers)
    v = phylax.check(plan, SafetyContext(role="child"))
    assert len(v) == 1
    assert v[0].rule == "permission.adult_only"
    # the same op by an adult clears
    assert phylax.check(plan, SafetyContext(role="adult")) == ()


def test_supervised_only_verb_needs_supervision() -> None:
    phylax = Phylax(Policy(supervised_only_verbs=frozenset({"operate_appliance"})))
    plan = Plan(subtasks=(_st("operate_appliance", ids=(1,)),))
    assert phylax.check(plan, SafetyContext(role="adult", supervised=False))[0].rule == (
        "supervision.required"
    )
    assert phylax.check(plan, SafetyContext(role="adult", supervised=True)) == ()


def test_over_speed_near_human_rejected() -> None:
    phylax = Phylax(Policy(max_speed_mps_near_human=0.3))
    plan = Plan(subtasks=(_st("navigate", ids=(1,), speed_mps=0.8),))
    v = phylax.check(plan, SafetyContext(humans_within_1m=True))
    assert v[0].rule == "proximity.speed_cap"
    # no human nearby -> the cap does not bite
    assert phylax.check(plan, SafetyContext(humans_within_1m=False)) == ()
    # slow enough near a human -> fine
    slow = Plan(subtasks=(_st("navigate", ids=(1,), speed_mps=0.2),))
    assert phylax.check(slow, SafetyContext(humans_within_1m=True)) == ()


def test_forbidden_zone_rejected() -> None:
    phylax = Phylax(Policy(forbidden_node_ids=frozenset({9})))
    plan = Plan(subtasks=(_st("navigate", ids=(9,)),))
    assert phylax.check(plan)[0].rule == "zone.forbidden"


def test_clean_plan_passes() -> None:
    phylax = Phylax(Policy(adult_only_verbs=frozenset({"grasp"})))
    plan = Plan(subtasks=(_st("navigate", ids=(1,)), _st("detect")))
    assert phylax.check(plan, SafetyContext(role="adult")) == ()


# --------------------------------------------------------------------------- #
# unit: untrusted skill-card vetting
# --------------------------------------------------------------------------- #
def test_unsigned_safety_card_refused() -> None:
    phylax = Phylax(Policy())  # trusts only provenance="builtin"
    unsafe = SkillCard.from_dict(
        {"id": "x", "safety": {"max_water_temperature_c": 90}, "provenance": "community-download"}
    )
    assert phylax.vet_card(unsafe) is False
    # a builtin card with the same safety annotation is trusted
    builtin = SkillCard.from_dict({"id": "x", "safety": {"a": 1}, "provenance": "builtin"})
    assert phylax.vet_card(builtin) is True
    # a card with no safety annotations is always fine, whatever its provenance
    plain = SkillCard.from_dict({"id": "x", "provenance": "community-download"})
    assert phylax.vet_card(plain) is True


# --------------------------------------------------------------------------- #
# integration through Brain.handle
# --------------------------------------------------------------------------- #
@pytest.fixture
def mem(tmp_path) -> SpatialMemory:
    m = SpatialMemory.open(tmp_path / "s.smem", embedding_dim=DIM)
    rng = np.random.default_rng(0).standard_normal(DIM).astype("float32")
    m.add_detections([Detection("knife", rng / np.linalg.norm(rng), (1, 0, 0.9),
                                (0.9, -0.1, 0.8), (1.1, 0.1, 1.0))])
    m.commit()
    return m


def _brain(mem: SpatialMemory, policy: Phylax) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner({"go": (Command("grasp", ("knife",)),)}),
        executor=MockBody(),
        policy=policy,
    )


def test_handle_blocks_unsafe_plan_and_speaks(mem: SpatialMemory) -> None:
    brain = _brain(mem, Phylax(Policy(adult_only_verbs=frozenset({"grasp"}))))
    r = brain.handle("go", safety_context=SafetyContext(role="child"))
    assert r.blocked
    assert r.violations[0].rule == "permission.adult_only"
    assert r.statuses == ()  # nothing dispatched (no reroute, no retry)
    assert r.plan is not None and r.plan.speak  # a refusal was spoken


def test_handle_dispatches_when_cleared(mem: SpatialMemory) -> None:
    brain = _brain(mem, Phylax(Policy(adult_only_verbs=frozenset({"grasp"}))))
    r = brain.handle("go", safety_context=SafetyContext(role="adult"))
    assert not r.blocked
    assert r.violations == ()
    assert [s.status for s in r.statuses] == [TaskStatus.SUCCESS]


def test_no_policy_dispatches_as_before(mem: SpatialMemory) -> None:
    # P1/P2 behavior is preserved when no policy is wired
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner({"go": (Command("grasp", ("knife",)),)}),
        executor=MockBody(),
    )
    r = brain.handle("go")
    assert not r.blocked
    assert [s.status for s in r.statuses] == [TaskStatus.SUCCESS]


def test_skillcardplanner_refuses_untrusted_safety_card(mem: SpatialMemory) -> None:
    card = SkillCard.from_dict(
        {
            "id": "shady_laundry",
            "category": "laundry",
            "safety": {"max_water_temperature_c": 90},
            "provenance": "community-download",
            "steps": [{"verb": "grasp", "target": "knife"}],
        }
    )
    planner = SkillCardPlanner(
        SkillLibrary([card]),
        MockBody().capabilities(),
        policy=Phylax(Policy()),  # trusts only builtins
    )
    # the untrusted safety card is refused -> no commands (no fallback wired)
    assert planner.plan("do the laundry", context="") == ()
