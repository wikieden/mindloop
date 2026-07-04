"""D-P advisory feedback into L3: low-reliability verbs are disclosed in the
planner context (the LLM sees them and can route around or pre-disclose);
healthy verbs stay a bare vocabulary word. Safety gates never read the score.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from bodylink import MockBody, g1d_manifest
from tempomem import Detection, TempoMem

from mindloop import Brain, ScriptedIntentRouter, ScriptedReasoner


class _CapturePlanner:
    """Records the context the brain hands the planner; plans nothing."""

    def __init__(self) -> None:
        self.context = ""

    def plan(self, instruction: str, context: str):
        self.context = context
        return ()


def _mem() -> TempoMem:
    mem = TempoMem.open(":memory:", embedding_dim=4)
    v = np.ones(4, dtype="float32") / 2.0
    mem.add_detections([Detection("mug", v, (0.5, 0.5, 0.8), (0.4, 0.4, 0.7), (0.6, 0.6, 0.9))])
    mem.commit()
    return mem


def _annotated_manifest():
    manifest = g1d_manifest()
    verbs = tuple(
        replace(v, reliability={"fragile": 0.55}) if v.name == "grasp" else v
        for v in manifest.verbs
    )
    return replace(manifest, verbs=verbs)


def test_low_reliability_verb_is_disclosed_in_planner_context() -> None:
    planner = _CapturePlanner()
    brain = Brain(
        _mem(),
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=planner,
        executor=MockBody(_annotated_manifest()),
    )
    brain.handle("bring me the mug")
    assert "grasp" in planner.context
    assert "fragile" in planner.context and "0.55" in planner.context


def test_healthy_verbs_stay_bare() -> None:
    planner = _CapturePlanner()
    brain = Brain(
        _mem(),
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=planner,
        executor=MockBody(),  # no reliability annotations at all
    )
    brain.handle("bring me the mug")
    assert "reliability" not in planner.context
