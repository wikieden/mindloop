"""Dynamic-scene P2 — symbolic effect write-back (WorldState overlay)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Answer,
    Brain,
    Command,
    EffectApplier,
    ScriptedIntentRouter,
    ScriptedPlanner,
    WorldState,
    parse_effect,
)

DIM = 16


# --------------------------------------------------------------------------- #
# WorldState unit
# --------------------------------------------------------------------------- #
def test_parse_effect() -> None:
    assert parse_effect("robot.holding=apple") is not None
    e = parse_effect("fridge.status=open")
    assert e is not None and e.key == "fridge.status" and e.value == "open"
    assert parse_effect("no_equals_here") is None
    assert parse_effect("=novalue") is None


def test_apply_bumps_version_only_on_change() -> None:
    w = WorldState()
    assert isinstance(w, EffectApplier)
    assert w.version == 0
    assert w.apply(("robot.holding=apple",)) == 1
    assert w.get("robot.holding") == "apple"
    # re-applying the same fact does not bump
    assert w.apply(("robot.holding=apple",)) == 1
    # a new/changed fact bumps
    assert w.apply(("robot.holding=cup",)) == 2
    assert w.get("robot.holding") == "cup"


def test_render_and_reset() -> None:
    w = WorldState()
    assert w.render() == ""
    w.apply(("fridge.status=open", "robot.holding=apple"))
    r = w.render()
    assert "fridge.status=open" in r and "robot.holding=apple" in r
    w.reset()
    assert w.snapshot() == {} and w.render() == ""


# --------------------------------------------------------------------------- #
# Brain integration — success writes back, context reflects it
# --------------------------------------------------------------------------- #
class _CtxReasoner:
    def __init__(self) -> None:
        self.last_context = ""

    def reason(self, question: str, context: str) -> Answer:
        self.last_context = context
        return Answer(text="ok [#1]", cited_node_ids=[1])


@pytest.fixture
def mem(tmp_path) -> TempoMem:
    m = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)
    rng = np.random.default_rng(0).standard_normal(DIM).astype("float32")
    m.add_detections(
        [
            Detection(
                "apple", rng / np.linalg.norm(rng), (1, 0, 0.9), (0.9, -0.1, 0.8), (1.1, 0.1, 1.0)
            )
        ]
    )
    m.commit()
    return m


def test_success_writes_effects_into_world(mem: TempoMem) -> None:
    body = MockBody()
    brain = Brain(
        mem,
        _CtxReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner({"grab": (Command("grasp", ("apple",)),)}),
        executor=body,
    )
    assert brain.world.version == 0
    r = brain.handle("grab")
    assert [s.status.value for s in r.statuses] == ["success"]
    # grasp's effect (robot.holding=apple) was written back from the success
    assert brain.world.get("robot.holding") == "apple"


def test_world_state_injected_into_next_context(mem: TempoMem) -> None:
    rsn = _CtxReasoner()
    brain = Brain(
        mem,
        rsn,
        router=ScriptedIntentRouter({"is it held?": "question"}, default="task"),
        planner=ScriptedPlanner({"grab": (Command("grasp", ("apple",)),)}),
        executor=MockBody(),
    )
    # before any action, no world-state block
    brain.handle("is it held?")
    assert "WORLD STATE" not in rsn.last_context
    # do the grasp (writes robot.holding=apple), then ask again
    brain.handle("grab")
    brain.handle("is it held?")
    assert "WORLD STATE" in rsn.last_context
    assert "robot.holding=apple" in rsn.last_context
