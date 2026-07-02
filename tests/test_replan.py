"""P4 — L4 trace + failure-driven replanning (network-free)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    ErrorCode,
    RecoveryHint,
    RecoveryKind,
    ReplanAction,
    Replanner,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    StatusUpdate,
    SubTask,
    TaskStatus,
    TraceStore,
)

DIM = 16


def _failed(verb: str, ids: tuple[int, ...], hint: RecoveryHint | None) -> StatusUpdate:
    return StatusUpdate(
        task_id="",
        subtask_id=f"s-{verb}",
        status=TaskStatus.FAILED,
        error_code=ErrorCode.GRASP_FAILED,
        recovery_actions=(hint,) if hint else (),
        touched_node_ids=ids,
    )


def _sub(verb: str, ids: tuple[int, ...] = (1,)) -> SubTask:
    return SubTask(id=f"s-{verb}", verb=verb, target_node_ids=ids)


# --------------------------------------------------------------------------- #
# TraceStore
# --------------------------------------------------------------------------- #
def test_trace_logs_and_queries_by_node() -> None:
    tr = TraceStore(":memory:")
    grasp, nav = _sub("grasp", (7,)), _sub("navigate", (7,))
    tr.log_attempt(grasp, _failed("grasp", (7,), None), session_id="s1")
    tr.log_attempt(
        nav,
        StatusUpdate("", "s-navigate", TaskStatus.SUCCESS, touched_node_ids=(7,)),
        session_id="s1",
    )
    eps = tr.episodes(session_id="s1")
    assert len(eps) == 2
    # queryable by node id (B9 audit chain into the trace)
    assert {r.verb for r in tr.by_node(7)} == {"grasp", "navigate"}
    # the failure view isolates negation-learning fuel
    fails = tr.failures()
    assert len(fails) == 1 and fails[0].verb == "grasp"
    tr.close()


# --------------------------------------------------------------------------- #
# Replanner — typed hint → bounded correction
# --------------------------------------------------------------------------- #
def test_position_offset_hint_adjusts() -> None:
    rp = Replanner()
    hint = RecoveryHint(RecoveryKind.POSITION_OFFSET, 0.02)
    d = rp.replan(_sub("grasp"), _failed("grasp", (1,), hint))
    assert d.action == ReplanAction.ADJUST
    assert d.subtasks[0].verb == "grasp"
    assert d.subtasks[0].params["recovery"] == "position_offset"
    assert d.subtasks[0].target_node_ids == (1,)  # node id preserved (B9)


def test_replan_hint_reroutes_with_navigate() -> None:
    rp = Replanner()
    d = rp.replan(_sub("grasp"), _failed("grasp", (1,), RecoveryHint(RecoveryKind.REPLAN)))
    assert d.action == ReplanAction.REROUTE
    assert [s.verb for s in d.subtasks] == ["navigate", "grasp"]


def test_retry_and_skip_hints() -> None:
    rp = Replanner()
    retry = rp.replan(_sub("grasp"), _failed("g", (1,), RecoveryHint(RecoveryKind.RETRY)))
    assert retry.action == ReplanAction.RETRY
    skip = rp.replan(_sub("detect"), _failed("d", (2,), RecoveryHint(RecoveryKind.SKIP)))
    assert skip.action == ReplanAction.SKIP


def test_no_hint_escalates() -> None:
    d = Replanner().replan(_sub("grasp"), _failed("grasp", (1,), None))
    assert d.action == ReplanAction.ESCALATE
    assert d.gives_up and d.speak


def test_per_target_cap_escalates() -> None:
    rp = Replanner(max_per_target=2)
    hint = RecoveryHint(RecoveryKind.POSITION_OFFSET, 0.02)
    sub = _sub("grasp")
    assert rp.replan(sub, _failed("grasp", (1,), hint)).action == ReplanAction.ADJUST  # 1
    assert rp.replan(sub, _failed("grasp", (1,), hint)).action == ReplanAction.ADJUST  # 2
    assert rp.replan(sub, _failed("grasp", (1,), hint)).action == ReplanAction.ESCALATE  # 3 > cap
    # a new task resets the counters
    rp.reset()
    assert rp.replan(sub, _failed("grasp", (1,), hint)).action == ReplanAction.ADJUST


def test_escalate_speak_uses_card_failure_hint() -> None:
    from mindloop import SkillCard

    card = SkillCard.from_dict({"id": "x", "failure_hints": ["Check the object isn't stuck."]})
    d = Replanner().replan(_sub("grasp"), _failed("grasp", (1,), None), card=card)
    assert d.speak == "Check the object isn't stuck."


# --------------------------------------------------------------------------- #
# Brain integration — the bounded replan loop
# --------------------------------------------------------------------------- #
class _FlakyBody(MockBody):
    """Fails the first dispatch of a verb (with a recovery hint), then succeeds."""

    def __init__(self, fail_once: dict[str, ErrorCode]) -> None:
        super().__init__()
        self._fail_once = dict(fail_once)
        self._seen: dict[str, int] = {}

    def _execute(self, subtask: SubTask) -> StatusUpdate:
        v = subtask.verb
        if v in self._fail_once and self._seen.get(v, 0) == 0:
            self._seen[v] = 1
            return StatusUpdate(
                "",
                subtask.id,
                TaskStatus.FAILED,
                error_code=self._fail_once[v],
                recovery_actions=(RecoveryHint(RecoveryKind.POSITION_OFFSET, 0.02),),
                touched_node_ids=subtask.target_node_ids,
            )
        return super()._execute(subtask)


@pytest.fixture
def mem(tmp_path) -> TempoMem:
    m = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)
    rng = np.random.default_rng(0).standard_normal(DIM).astype("float32")
    m.add_detections(
        [
            Detection(
                "bottle", rng / np.linalg.norm(rng), (1, 0, 0.9), (0.9, -0.1, 0.8), (1.1, 0.1, 1.0)
            )
        ]
    )
    m.commit()
    return m


def _brain(mem: TempoMem, body: MockBody, trace: TraceStore | None = None) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner({"go": (Command("grasp", ("bottle",)),)}),
        executor=body,
        replanner=Replanner(),
        trace=trace,
    )


def test_handle_recovers_via_replan(mem: TempoMem) -> None:
    trace = TraceStore(":memory:")
    brain = _brain(mem, _FlakyBody({"grasp": ErrorCode.GRASP_FAILED}), trace)
    r = brain.handle("go")
    # grasp failed once, replan adjusted, retry succeeded
    assert r.statuses[-1].status == TaskStatus.SUCCESS
    # the trace recorded both attempts, citing the bottle's node id (B9)
    assert len(trace.episodes()) == 2
    assert len(trace.failures()) == 1
    assert trace.by_node(1)  # bottle node id touched
    trace.close()


def test_handle_escalates_when_unrepairable(mem: TempoMem) -> None:
    # a permanent failure -> bounded retries -> escalate (stop + speak, no infinite loop)
    brain = _brain(mem, MockBody(fail={"grasp": ErrorCode.GRASP_FAILED}))
    r = brain.handle("go")
    assert r.statuses[-1].status == TaskStatus.FAILED
    assert r.plan is not None and "grasp" in r.plan.speak.lower()  # escalation spoken


def test_no_replanner_dispatches_once(mem: TempoMem) -> None:
    # without a replanner, a failure is just reported (P1-P3 behavior preserved)
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner({"go": (Command("grasp", ("bottle",)),)}),
        executor=MockBody(fail={"grasp": ErrorCode.GRASP_FAILED}),
    )
    r = brain.handle("go")
    assert r.statuses[-1].status == TaskStatus.FAILED
    # no escalation: speak is just the compiled default floor, not a repair message
    assert r.plan is not None and r.plan.speak == "OK." and "grasp" not in r.plan.speak.lower()
