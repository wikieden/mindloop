"""Dynamic-scene P3 — idempotent dispatch (skip steps the world already satisfies)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    SubTask,
    TaskStatus,
)

DIM = 16


class _CountBody(MockBody):
    """MockBody that records each verb it actually executes (skips never reach it)."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def _execute(self, subtask: SubTask):
        self.calls.append(subtask.verb)
        return super()._execute(subtask)


@pytest.fixture
def mem(tmp_path) -> TempoMem:
    m = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)
    rng = np.random.default_rng(0).standard_normal(DIM).astype("float32")
    m.add_detections([Detection("apple", rng / np.linalg.norm(rng), (1, 0, 0.9),
                                (0.9, -0.1, 0.8), (1.1, 0.1, 1.0))])
    m.commit()
    return m


def _brain(mem: TempoMem, body: MockBody, plan: dict) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner(plan),
        executor=body,
    )


def test_second_grasp_of_same_object_is_skipped(mem: TempoMem) -> None:
    body = _CountBody()
    brain = _brain(mem, body, {"go": (Command("grasp", ("apple",)), Command("grasp", ("apple",)))})
    r = brain.handle("go")
    assert len(r.statuses) == 2
    assert all(s.status == TaskStatus.SUCCESS for s in r.statuses)
    assert "already satisfied" in r.statuses[1].message
    # the body executed grasp once; the redundant second grasp was skipped
    assert body.calls == ["grasp"]
    assert brain.world.get("robot.holding") == "apple"


def test_distinct_steps_are_not_skipped(mem: TempoMem) -> None:
    body = _CountBody()
    plan = {"go": (Command("navigate", ("apple",)), Command("grasp", ("apple",)))}
    brain = _brain(mem, body, plan)
    brain.handle("go")
    # different effects -> both dispatched (no false skip)
    assert body.calls == ["navigate", "grasp"]


def test_no_effect_step_is_never_skipped(mem: TempoMem) -> None:
    body = _CountBody()
    brain = _brain(mem, body, {"go": (Command("detect", ()), Command("detect", ()))})
    brain.handle("go")
    # detect carries no effects -> can't be confirmed done -> always dispatched
    assert body.calls == ["detect", "detect"]
