"""Dynamic-scene P4 — active perception re-look → bounded tail re-plan (network-free)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    ActivePerception,
    Brain,
    Command,
    DefaultSceneContextProvider,
    ScriptedIntentRouter,
    ScriptedPerception,
    ScriptedReasoner,
    TaskStatus,
)

DIM = 16


def _det(name: str, seed: int, c: tuple[float, float, float]) -> Detection:
    v = np.random.default_rng(seed).standard_normal(DIM).astype("float32")
    lo = (c[0] - 0.05, c[1] - 0.05, c[2] - 0.05)
    hi = (c[0] + 0.05, c[1] + 0.05, c[2] + 0.05)
    return Detection(name, v / np.linalg.norm(v), c, lo, hi)


class _CountPlanner:
    """Returns a fixed command sequence; counts how often it is asked to plan."""

    def __init__(self, cmds: tuple[Command, ...]) -> None:
        self._cmds = cmds
        self.calls = 0

    def plan(self, instruction: str, context: str) -> tuple[Command, ...]:
        self.calls += 1
        return self._cmds


@pytest.fixture
def mem(tmp_path) -> TempoMem:
    m = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)
    m.add_detections([_det("apple", 1, (1.0, 0.0, 0.9))])
    m.commit()
    return m


def _brain(mem, planner, perception=None, provider=None) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=planner,
        executor=MockBody(),
        active_perception=perception,
        context_provider=provider,
    )


def test_scripted_perception_fires_once_per_step() -> None:
    ap = ScriptedPerception({1: [_det("cup", 2, (0.0, 0.0, 0.5))]})
    assert isinstance(ap, ActivePerception)
    assert ap.perceive(step_index=0, last_status=None) is None
    got = ap.perceive(step_index=1, last_status=None)
    assert got is not None and got[0].label == "cup"
    # fires only once
    assert ap.perceive(step_index=1, last_status=None) is None


def test_relook_triggers_bounded_tail_replan(mem: TempoMem) -> None:
    planner = _CountPlanner((Command("navigate", ("apple",)), Command("grasp", ("apple",))))
    provider = DefaultSceneContextProvider(mem)
    # a new object appears just before step 1 (the grasp)
    ap = ScriptedPerception({1: [_det("cup", 2, (0.0, 0.0, 0.5))]})
    brain = _brain(mem, planner, perception=ap, provider=provider)

    r = brain.handle("fetch the apple")

    # the re-look fused a detection (map version bumped) and forced one re-plan
    assert planner.calls == 2  # initial plan + one tail re-plan
    assert provider.version >= 1  # ingest bumped the map version
    # the spliced re-plan's already-done navigate was idempotently skipped
    assert any("already satisfied" in s.message for s in r.statuses)
    assert r.statuses[-1].status == TaskStatus.SUCCESS


def test_no_perception_plans_once(mem: TempoMem) -> None:
    planner = _CountPlanner((Command("navigate", ("apple",)), Command("grasp", ("apple",))))
    brain = _brain(mem, planner)
    brain.handle("fetch the apple")
    assert planner.calls == 1  # no re-look, no re-plan


def test_tail_replan_is_bounded(mem: TempoMem) -> None:
    # perception would re-look at every step, but max_tail_replans caps it
    planner = _CountPlanner((Command("navigate", ("apple",)), Command("grasp", ("apple",))))
    ap = ScriptedPerception({0: [_det("a", 3, (0, 0, 0.4))], 1: [_det("b", 4, (0, 0, 0.6))]})
    brain = Brain(
        mem, ScriptedReasoner(), router=ScriptedIntentRouter(default="task"),
        planner=planner, executor=MockBody(), active_perception=ap, max_tail_replans=1,
    )
    brain.handle("fetch the apple")
    assert planner.calls == 2  # initial + exactly one re-plan (bounded), not more
