"""T5-10 small batch — negation_constraints (B2R parity), the FMEA-derived
conservative Policy preset, and the owner access-control override.

* A replanned retry carries `negation_constraints` naming the failed attempt
  (machine-splittable ``not:<verb>:<failed id>``, citing the trace row), so a
  lower tier can avoid repeating exactly what just failed. Accumulates.
* `conservative_policy()` is the FMEA-hardened preset (stove/oven + sharp-tool
  param gates, tighter human-proximity speed cap) — the recommended P7.4
  `offline_policy` fill.
* `Phylax.replace_policy` is the ONLY runtime policy override, gated to
  role=adult (owner-class); anything else is refused loudly and the standing
  policy is untouched. No path reaches it from barge/clarify answers — a
  guest cannot talk the gate open (D-O no-self-escalation).
"""

from __future__ import annotations

import pytest

from mindloop import (
    ErrorCode,
    Phylax,
    Plan,
    Policy,
    RecoveryHint,
    RecoveryKind,
    Replanner,
    SafetyContext,
    StatusUpdate,
    SubTask,
    TaskStatus,
    conservative_policy,
)


def _failed(sub: SubTask, hint: RecoveryKind = RecoveryKind.RETRY) -> StatusUpdate:
    return StatusUpdate(
        task_id="t",
        subtask_id=sub.id,
        status=TaskStatus.FAILED,
        error_code=ErrorCode.GRASP_FAILED,
        recovery_actions=(RecoveryHint(hint),),
    )


def test_replanned_retry_carries_negation_of_the_failed_attempt() -> None:
    rp = Replanner()
    sub = SubTask(id="a0", verb="grasp", target_node_ids=(7,))
    decision = rp.replan(sub, _failed(sub))
    assert decision.subtasks
    retry = decision.subtasks[-1]
    assert f"not:grasp:{sub.id}" in retry.negation_constraints


def test_negations_accumulate_across_repeated_failures() -> None:
    rp = Replanner()
    sub = SubTask(id="a0", verb="grasp", target_node_ids=(7,))
    first_retry = rp.replan(sub, _failed(sub)).subtasks[-1]
    second_retry = rp.replan(first_retry, _failed(first_retry)).subtasks[-1]
    assert f"not:grasp:{sub.id}" in second_retry.negation_constraints
    assert f"not:grasp:{first_retry.id}" in second_retry.negation_constraints


def test_conservative_policy_gates_stove_and_sharp_tools() -> None:
    gate = Phylax(conservative_policy())
    stove = Plan(
        subtasks=(
            SubTask(
                id="s0",
                verb="operate_appliance",
                params={"appliance_type": "stove"},
            ),
        )
    )
    knife = Plan(
        subtasks=(SubTask(id="k0", verb="grasp", named_params={"target": "knife"}),)
    )
    child = SafetyContext(role="child")
    assert gate.check(stove, child)
    assert gate.check(knife, child)
    # an adult passes both — conservative, not paralyzed
    adult = SafetyContext(role="adult")
    assert not gate.check(stove, adult)
    assert not gate.check(knife, adult)


def test_owner_override_swaps_the_standing_policy() -> None:
    gate = Phylax(Policy())
    plan = Plan(subtasks=(SubTask(id="g0", verb="grasp", named_params={"target": "knife"}),))
    assert not gate.check(plan, SafetyContext(role="child"))  # open policy
    gate.replace_policy(conservative_policy(), actor_role="adult")
    assert gate.check(plan, SafetyContext(role="child"))  # tightened at runtime


def test_non_adult_override_is_refused_and_policy_untouched() -> None:
    gate = Phylax(conservative_policy())
    plan = Plan(
        subtasks=(
            SubTask(id="s0", verb="operate_appliance", params={"appliance_type": "stove"}),
        )
    )
    for role in ("child", "guest", "stranger"):
        with pytest.raises(PermissionError):
            gate.replace_policy(Policy(), actor_role=role)  # tries to LOOSEN
    assert gate.check(plan, SafetyContext(role="child"))  # still tight
