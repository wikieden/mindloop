"""P0 — executor seam contract (D1/D3/B3/B9). Pure value-type tests, no body."""

from __future__ import annotations

from collections.abc import Iterator

from mindloop import (
    BodyProfile,
    CapabilityManifest,
    ErrorCode,
    ExecutorAdapter,
    HealthReport,
    RecoveryHint,
    RecoveryKind,
    ScriptedReasoner,
    StatusUpdate,
    SubTask,
    TaskStatus,
    VerbSpec,
)
from mindloop.brain import Brain


def _g1d_manifest() -> CapabilityManifest:
    """A B10-shaped G1-D manifest: wheeled 32-DOF, the declared verb set."""
    return CapabilityManifest(
        body_profile=BodyProfile("g1d", "Unitree G1-D", dof=32, base_type="wheeled"),
        verbs=(
            VerbSpec("navigate", params=("target",)),
            VerbSpec("grasp", params=("target",)),
            VerbSpec("place", params=("target", "location")),
            VerbSpec("detect"),
            VerbSpec("open_door", params=("target",)),
            VerbSpec("charging"),
        ),
    )


def test_task_status_is_terminal() -> None:
    assert TaskStatus.SUCCESS.is_terminal
    assert TaskStatus.FAILED.is_terminal
    assert TaskStatus.ABORTED.is_terminal
    assert not TaskStatus.RUNNING.is_terminal
    assert not TaskStatus.PAUSED.is_terminal


def test_error_codes_are_typed_strings() -> None:
    # B3: typed ERR_* enum, never free text.
    assert ErrorCode.GRASP_FAILED.value == "ERR_GRASP_FAILED"
    assert ErrorCode("ERR_OBJECT_LOST") is ErrorCode.OBJECT_LOST


def test_manifest_supports_only_declared_verbs() -> None:
    # D3: a verb the body does not declare is refused, never dispatched.
    m = _g1d_manifest()
    assert m.supports("grasp")
    assert m.supports("charging")
    assert not m.supports("fly")
    assert not m.supports("cook")
    assert m.verb_names() == {"navigate", "grasp", "place", "detect", "open_door", "charging"}
    assert m.body_profile.base_type == "wheeled"  # no legged locomotion (B10)


def test_subtask_carries_node_ids_not_joint_space() -> None:
    # B9: node ids cross the seam; B8/D3: no joint angles / base-frame poses.
    st = SubTask(id="s1", verb="grasp", target_node_ids=(12,), params={"grip": "side"})
    assert st.target_node_ids == (12,)
    assert "joint" not in st.params and "pose" not in st.params


def test_status_update_echoes_node_ids_and_typed_recovery() -> None:
    # B9 echo-back + B3 typed recovery vocabulary.
    upd = StatusUpdate(
        task_id="t1",
        subtask_id="s1",
        status=TaskStatus.FAILED,
        error_code=ErrorCode.GRASP_FAILED,
        recovery_actions=(RecoveryHint(RecoveryKind.POSITION_OFFSET, 0.02),),
        touched_node_ids=(12,),
    )
    assert upd.status.is_terminal
    assert upd.touched_node_ids == (12,)
    assert upd.recovery_actions[0].kind is RecoveryKind.POSITION_OFFSET


def test_executor_adapter_is_runtime_checkable() -> None:
    class _Fake:
        def capabilities(self) -> CapabilityManifest:
            return _g1d_manifest()

        def dispatch(self, subtask: SubTask) -> Iterator[StatusUpdate]:
            yield StatusUpdate("t", subtask.id, TaskStatus.SUCCESS, progress=1.0)

    assert isinstance(_Fake(), ExecutorAdapter)
    assert not isinstance(object(), ExecutorAdapter)


def test_brain_health_reports_readiness(mem) -> None:
    # B5: reasoner + memory ready; skill library lands in P2 (None for now).
    brain = Brain(mem, ScriptedReasoner())
    h = brain.health()
    assert isinstance(h, HealthReport)
    assert h.reasoner_ready and h.memory_ready
    assert h.skill_library_ready is None
    assert h.ok
