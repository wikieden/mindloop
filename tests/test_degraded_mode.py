"""P7.4 — degraded (offline) mode: telemetry + conservative tighten + honest UX.

A `mode_probe` (typically ``lambda: failover.mode``) tells the brain which
verbalizer tier served the turn. Offline (``"fallback"``): the turn is stamped
and traced (verb ``serve_mode``), an optional stricter `offline_policy`
replaces the Phylax gate (tighten-only — swap-in, never loosen), and a task's
speak line honestly discloses the offline state. Skill-card preference offline
is structural (SkillCardPlanner is card-first, local; only its LLM fallback
degrades).
"""

from __future__ import annotations

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    Phylax,
    Policy,
    SafetyContext,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    TraceStore,
)

_PLANS = {"grab the mug": (Command("grasp", ("mug",)),)}


def _mem() -> TempoMem:
    mem = TempoMem.open(":memory:", embedding_dim=4)
    v = np.ones(4, dtype="float32") / 2.0
    mem.add_detections([Detection("mug", v, (0.5, 0.5, 0.8), (0.4, 0.4, 0.7), (0.6, 0.6, 0.9))])
    mem.commit()
    return mem


def _brain(*, mode: str | None = None, offline_policy: Phylax | None = None, trace=None) -> Brain:
    return Brain(
        _mem(),
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=ScriptedPlanner(_PLANS),
        executor=MockBody(),
        trace=trace,
        mode_probe=(lambda: mode) if mode is not None else None,
        offline_policy=offline_policy,
    )


def test_result_is_stamped_with_the_serving_mode() -> None:
    assert _brain(mode="primary").handle("grab the mug").mode == "primary"
    assert _brain(mode="fallback").handle("grab the mug").mode == "fallback"
    assert _brain().handle("grab the mug").mode == ""  # no probe -> unknown


def test_offline_task_speak_discloses_honestly() -> None:
    online = _brain(mode="primary").handle("grab the mug")
    offline = _brain(mode="fallback").handle("grab the mug")
    assert "offline" not in (online.plan.speak if online.plan else "")
    assert offline.plan is not None and "offline" in offline.plan.speak


def test_offline_policy_tightens_the_gate() -> None:
    strict = Phylax(Policy(adult_only_verbs=frozenset({"grasp"})))
    ctx = SafetyContext(role="child")
    # online: no gate at all -> dispatches
    r1 = _brain(mode="primary", offline_policy=strict).handle("grab the mug", safety_context=ctx)
    assert not r1.blocked and r1.statuses
    # offline: the conservative gate takes over -> blocked, nothing dispatched
    r2 = _brain(mode="fallback", offline_policy=strict).handle("grab the mug", safety_context=ctx)
    assert r2.blocked and r2.statuses == ()


def test_serving_mode_is_traced_per_task_turn() -> None:
    tr = TraceStore(":memory:")
    _brain(mode="fallback", trace=tr).handle("grab the mug")
    rows = [r for r in tr.episodes(limit=100) if r.verb == "serve_mode"]
    assert rows and "fallback" in rows[0].detail
    tr.close()
