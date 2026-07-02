"""P6 — scenario eval harness (network-free): planning / policy / replan metrics."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    ErrorCode,
    EvalCase,
    EvalThresholds,
    Phylax,
    Policy,
    RecoveryHint,
    RecoveryKind,
    Replanner,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    StatusUpdate,
    SubTask,
    TaskStatus,
    run_eval,
)

DIM = 16


class _FlakyBody(MockBody):
    def __init__(self, fail_once: dict[str, ErrorCode]) -> None:
        super().__init__()
        self._fail_once = dict(fail_once)
        self._seen: dict[str, int] = {}

    def _execute(self, subtask: SubTask) -> StatusUpdate:
        v = subtask.verb
        if v in self._fail_once and self._seen.get(v, 0) == 0:
            self._seen[v] = 1
            return StatusUpdate(
                "", subtask.id, TaskStatus.FAILED,
                error_code=self._fail_once[v],
                recovery_actions=(RecoveryHint(RecoveryKind.POSITION_OFFSET, 0.02),),
                touched_node_ids=subtask.target_node_ids,
            )
        return super()._execute(subtask)


@pytest.fixture
def brain(tmp_path) -> Brain:
    mem = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)

    def f(s: int) -> np.ndarray:
        v = np.random.default_rng(s).standard_normal(DIM).astype("float32")
        return v / np.linalg.norm(v)

    mem.add_detections(
        [
            Detection("bottle", f(1), (1, 0, 0.9), (0.9, -0.1, 0.8), (1.1, 0.1, 1.0)),
            Detection("door", f(2), (2, 0, 1.0), (1.9, -0.1, 0.0), (2.1, 0.1, 2.0)),
        ]
    )
    mem.commit()
    return Brain(
        mem,
        ScriptedReasoner({"what is here?": "a bottle [#1]"}),
        router=ScriptedIntentRouter({"what is here?": "question"}, default="task"),
        planner=ScriptedPlanner(
            {
                "bring the bottle": (Command("grasp", ("bottle",)),),
                "open the door": (Command("open_door", ("door",)),),
            }
        ),
        executor=_FlakyBody({"grasp": ErrorCode.GRASP_FAILED}),
        policy=Phylax(Policy(adult_only_verbs=frozenset({"grasp"}))),
        replanner=Replanner(),
    )


def test_eval_all_dimensions_pass(brain: Brain) -> None:
    cases = [
        EvalCase("what is here?", role="adult", expect_intent="question"),
        # planning + replan-recovery: grasp fails once then recovers
        EvalCase("bring the bottle", role="adult", expect_verbs=("grasp",), expect_success=True),
        # policy: a child is blocked from the adult-only grasp
        EvalCase("bring the bottle", role="child", expect_blocked=True),
        # policy pass + planning for a non-gated verb
        EvalCase("open the door", role="adult", expect_blocked=False, expect_verbs=("open_door",)),
    ]
    report = run_eval(brain, cases)
    assert report.intent_accuracy == 1.0
    assert report.planning_accuracy == 1.0
    assert report.policy_compliance == 1.0
    assert report.replan_success == 1.0
    assert report.meets(EvalThresholds())
    assert report.failures == []


def test_eval_catches_a_regression(brain: Brain) -> None:
    # an expectation the brain does NOT meet -> scored as a miss, meets() False
    bad = [EvalCase("bring the bottle", role="adult", expect_verbs=("navigate", "grasp"))]
    report = run_eval(brain, bad)
    assert report.planning_accuracy == 0.0
    assert not report.meets()
    assert report.failures and "plan[" in report.failures[0]


def test_unexercised_dimension_passes_vacuously(brain: Brain) -> None:
    # only intent is scored -> the other dimensions are vacuously 1.0
    report = run_eval(brain, [EvalCase("what is here?", expect_intent="question")])
    assert report.planning_total == 0
    assert report.planning_accuracy == 1.0
    assert report.meets()
