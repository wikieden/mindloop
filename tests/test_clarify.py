"""3b slice 3 — Clarifier seam (D3): dead-end ESCALATE routes to a human
question when a clarifier is wired; the answer is an instruction (Phylax
re-vets it); the ask budget is ≤2 per task and exceeding it stops honestly."""

from __future__ import annotations

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    ErrorCode,
    Phylax,
    Policy,
    Replanner,
    SafetyContext,
    ScriptedClarifier,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    TraceStore,
)

_DIM = 8


def _mem(*names: str) -> TempoMem:
    mem = TempoMem.open(":memory:", embedding_dim=_DIM)
    rng = np.random.default_rng(0)
    for i, name in enumerate(names):
        v = rng.standard_normal(_DIM).astype("float32")
        c = (float(i), 0.0, 0.5)
        mem.add_detections(
            [
                Detection(
                    name,
                    v / np.linalg.norm(v),
                    c,
                    (c[0] - 0.1, -0.1, 0.4),
                    (c[0] + 0.1, 0.1, 0.6),
                )
            ]
        )
    mem.commit()
    return mem


_GRAB = {"grab the apple": (Command("grasp", ("apple",)),)}


def _brain(mem, *, plans, clarifier=None, policy=None, trace=None, fail=None) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=ScriptedPlanner(plans),
        executor=MockBody(fail=fail or {}),
        replanner=Replanner(),
        clarifier=clarifier,
        policy=policy,
        trace=trace,
    )


def test_dead_end_escalate_asks_and_resolves() -> None:
    mem = _mem("apple")
    plans = dict(_GRAB)
    # the clarified goal re-plans to a verb that does not fail
    plans["grab the apple (use the tray instead)"] = (Command("navigate", ("apple",)),)
    clarifier = ScriptedClarifier(default="use the tray instead")
    r = _brain(
        mem,
        plans=plans,
        clarifier=clarifier,
        fail={"grasp": ErrorCode.BATTERY_LOW},
    ).handle("grab the apple")
    assert clarifier.asked  # the robot did ask
    assert r.statuses and r.statuses[-1].status.value == "success"


def test_ask_budget_caps_then_honest_stop() -> None:
    mem = _mem("apple")
    # every clarified re-plan still grasps -> still fails -> escalates again
    plans = {
        "grab the apple": (Command("grasp", ("apple",)),),
        "grab the apple (keep trying)": (Command("grasp", ("apple",)),),
        "grab the apple (keep trying) (keep trying)": (Command("grasp", ("apple",)),),
        "grab the apple (keep trying) (keep trying) (keep trying)": (Command("grasp", ("apple",)),),
    }
    clarifier = ScriptedClarifier(default="keep trying")
    r = _brain(mem, plans=plans, clarifier=clarifier, fail={"grasp": ErrorCode.BATTERY_LOW}).handle(
        "grab the apple"
    )
    assert len(clarifier.asked) == 2  # budget <=2 per task
    assert r.plan.speak  # honest escalation speak after the budget ran out


def test_no_clarifier_escalates_as_before() -> None:
    mem = _mem("apple")
    r = _brain(mem, plans=dict(_GRAB), fail={"grasp": ErrorCode.BATTERY_LOW}).handle(
        "grab the apple"
    )
    assert r.plan.speak  # escalation surfaced, nothing asked


def test_clarifier_answer_is_re_vetted_by_phylax() -> None:
    mem = _mem("apple", "knife")
    plans = dict(_GRAB)
    # the "answer" tries to smuggle in an adult-only action
    plans["grab the apple (grab the knife instead)"] = (Command("grasp", ("knife",)),)
    clarifier = ScriptedClarifier(default="grab the knife instead")
    policy = Phylax(Policy(adult_only_verbs=frozenset({"grasp"})))
    # child context: original grasp is ALSO adult-only, so gate the whole thing:
    # use a policy-free original path via navigate, failing on navigate instead
    plans["grab the apple"] = (Command("navigate", ("apple",)),)
    plans["grab the apple (grab the knife instead)"] = (Command("grasp", ("knife",)),)
    r = _brain(
        mem,
        plans=plans,
        clarifier=clarifier,
        policy=policy,
        fail={"navigate": ErrorCode.BATTERY_LOW},
    ).handle("grab the apple", safety_context=SafetyContext(role="child"))
    assert clarifier.asked
    assert not any(st.status.value == "success" for st in r.statuses)
    assert r.plan.speak  # refusal or escalation spoken, never dispatched


def test_ask_is_traced() -> None:
    mem = _mem("apple")
    plans = dict(_GRAB)
    plans["grab the apple (use the tray instead)"] = (Command("navigate", ("apple",)),)
    trace = TraceStore(":memory:")
    _brain(
        mem,
        plans=plans,
        clarifier=ScriptedClarifier(default="use the tray instead"),
        trace=trace,
        fail={"grasp": ErrorCode.BATTERY_LOW},
    ).handle("grab the apple")
    verbs = [rec.verb for rec in trace.episodes(limit=100)]
    assert "ask_human" in verbs
    trace.close()
