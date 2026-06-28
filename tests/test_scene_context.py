"""Dynamic-scene P1 — SceneContextProvider seam (behavior-preserving + version)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, SpatialMemory

from mindloop import (
    Brain,
    Command,
    DefaultSceneContextProvider,
    Focus,
    SceneContextProvider,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
)

DIM = 16


@pytest.fixture
def mem(tmp_path) -> SpatialMemory:
    m = SpatialMemory.open(tmp_path / "s.smem", embedding_dim=DIM)

    def f(s: int) -> np.ndarray:
        v = np.random.default_rng(s).standard_normal(DIM).astype("float32")
        return v / np.linalg.norm(v)

    m.add_detections(
        [
            Detection("bottle", f(1), (1, 0, 0.9), (0.9, -0.1, 0.8), (1.1, 0.1, 1.0)),
            Detection("lamp", f(2), (3, 2, 1.2), (2.9, 1.9, 1.1), (3.1, 2.1, 1.3)),
        ]
    )
    m.commit()
    return m


def test_provider_returns_text_and_version(mem: SpatialMemory) -> None:
    p = DefaultSceneContextProvider(mem)
    text, version = p.context(Focus(query="bottle"))
    assert isinstance(text, str) and text  # non-empty serialized scene
    assert version == 0
    assert isinstance(p, SceneContextProvider)


def test_bump_advances_version(mem: SpatialMemory) -> None:
    p = DefaultSceneContextProvider(mem)
    assert p.version == 0
    assert p.bump() == 1
    _, v = p.context(Focus(query="bottle"))
    assert v == 1


def test_focus_node_ids_union_keeps_targets_in_view(mem: SpatialMemory) -> None:
    p = DefaultSceneContextProvider(mem)
    # query for 'bottle' alone; then force the lamp (node 2) into view via focus
    base, _ = p.context(Focus(query="bottle"))
    with_lamp, _ = p.context(Focus(query="bottle", node_ids=(2,)))
    assert "lamp" in with_lamp
    # the forced node only appears because focus pinned it
    assert ("lamp" in base) is False or with_lamp != base


def test_empty_query_falls_back_to_whole_scene(mem: SpatialMemory) -> None:
    p = DefaultSceneContextProvider(mem)
    text, _ = p.context(Focus(query="nonexistent_xyzzy"))
    assert text  # whole-scene fallback, not empty


# --------------------------------------------------------------------------- #
# Brain integration — behavior preserved, version bumps on perception
# --------------------------------------------------------------------------- #
def test_brain_uses_provider_and_bumps_on_ingest(mem: SpatialMemory) -> None:
    provider = DefaultSceneContextProvider(mem, default_budget=1500)
    brain = Brain(
        mem,
        ScriptedReasoner({"what is here?": "a bottle [#1]"}),
        router=ScriptedIntentRouter({"what is here?": "question"}, default="task"),
        planner=ScriptedPlanner({"go": (Command("grasp", ("bottle",)),)}),
        executor=MockBody(),
        context_provider=provider,
    )
    assert provider.version == 0
    # ask still works through the provider (behavior preserved)
    ans = brain.handle("what is here?")
    assert ans.answer is not None and ans.answer.cited_node_ids == [1]
    # a perception write bumps the map version
    brain.ingest([Detection("cup", np.ones(DIM, "float32") / np.sqrt(DIM),
                            (0, 0, 0.5), (-0.1, -0.1, 0.4), (0.1, 0.1, 0.6))])
    assert provider.version == 1
