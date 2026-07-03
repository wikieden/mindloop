"""3b slice 2 — the dispatch loop polls the interrupt inbox between steps
(D-E precision) and acts on the BargeDecision: abort / answer+resume /
supersede / correction, with Phylax re-vetting any barge-triggered re-plan."""

from __future__ import annotations

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    Phylax,
    Policy,
    QueueInterruptSource,
    SafetyContext,
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


class _PushOnFirstStep(MockBody):
    """Pushes an utterance into the inbox during the FIRST dispatched step, so
    the loop-top poll sees it before step 2 (between-step precision, D-E)."""

    def __init__(self, source: QueueInterruptSource, utterance: str) -> None:
        super().__init__()
        self._source = source
        self._utterance = utterance
        self._pushed = False

    def _execute(self, subtask):  # type: ignore[override]
        if not self._pushed:
            self._pushed = True
            self._source.push(self._utterance)
        return super()._execute(subtask)


class _Recorder:
    """Speaker stub recording everything said."""

    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text: str) -> None:
        self.said.append(text)


_ROUTER = {
    "what year was this built?": "question",
}


def _brain(mem, source, body, *, planner_plans, speaker=None, policy=None, trace=None) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner({"what year was this built?": "in 1932 [#1]"}),
        router=ScriptedIntentRouter(dict(_ROUTER), default="task"),
        planner=ScriptedPlanner(planner_plans),
        executor=body,
        interrupts=source,
        speaker=speaker,
        policy=policy,
        trace=trace,
    )


_FETCH = {"fetch the bottle": (Command("navigate", ("bottle",)), Command("grasp", ("bottle",)))}


def _messages(result) -> list[str]:
    return [st.message for st in result.statuses]


def test_abort_stops_remaining_steps() -> None:
    mem = _mem("bottle")
    src = QueueInterruptSource()
    body = _PushOnFirstStep(src, "stop")
    r = _brain(mem, src, body, planner_plans=_FETCH).handle("fetch the bottle")
    assert len(r.statuses) == 1  # step 2 never dispatched
    assert "stopping" in r.plan.speak.lower()


def test_chitchat_answers_and_resumes() -> None:
    mem = _mem("bottle")
    src = QueueInterruptSource()
    body = _PushOnFirstStep(src, "what year was this built?")
    speaker = _Recorder()
    r = _brain(mem, src, body, planner_plans=_FETCH, speaker=speaker).handle("fetch the bottle")
    assert len(r.statuses) == 2  # resumed: full plan completed
    assert any("1932" in s for s in speaker.said)


def test_supersede_replaces_remaining_plan() -> None:
    mem = _mem("bottle", "mug")
    src = QueueInterruptSource()
    body = _PushOnFirstStep(src, "bring me the mug")
    plans = dict(_FETCH)
    plans["bring me the mug"] = (Command("grasp", ("mug",)),)
    r = _brain(mem, src, body, planner_plans=plans).handle("fetch the bottle")
    msgs = _messages(r)
    assert msgs[0] == "mock navigate ok"  # step 1 of the old plan ran
    assert msgs[1:] == ["mock grasp ok"]  # then the NEW goal's plan, old grasp dropped
    assert len(msgs) == 2


def test_correction_replans_same_goal_with_fix() -> None:
    mem = _mem("bottle")
    src = QueueInterruptSource()
    body = _PushOnFirstStep(src, "no, the red one")
    plans = dict(_FETCH)
    plans["fetch the bottle (no, the red one)"] = (Command("grasp", ("bottle",)),)
    r = _brain(mem, src, body, planner_plans=plans).handle("fetch the bottle")
    msgs = _messages(r)
    assert msgs == ["mock navigate ok", "mock grasp ok"]


def test_superseding_plan_is_re_vetted_by_phylax() -> None:
    mem = _mem("bottle", "knife")
    src = QueueInterruptSource()
    body = _PushOnFirstStep(src, "grab the knife")
    # original plan uses only navigate (open to all); the superseding plan
    # introduces the adult-only grasp — that is what the re-vet must catch
    plans = {
        "fetch the bottle": (Command("navigate", ("bottle",)), Command("navigate", ("knife",)))
    }
    plans["grab the knife"] = (Command("grasp", ("knife",)),)
    policy = Phylax(Policy(adult_only_verbs=frozenset({"grasp"})))
    r = _brain(mem, src, body, planner_plans=plans, policy=policy).handle(
        "fetch the bottle", safety_context=SafetyContext(role="child")
    )
    # step 1 (navigate) ran; the superseding grasp plan was blocked, not dispatched
    assert _messages(r) == ["mock navigate ok"]  # second navigate dropped too
    assert "adult" in r.plan.speak.lower() or "can't" in r.plan.speak.lower()


def test_barge_decision_is_traced() -> None:
    mem = _mem("bottle")
    src = QueueInterruptSource()
    body = _PushOnFirstStep(src, "stop")
    trace = TraceStore(":memory:")
    _brain(mem, src, body, planner_plans=_FETCH, trace=trace).handle("fetch the bottle")
    verbs = [r.verb for r in trace.episodes(limit=100)]
    assert "barge_in" in verbs
    trace.close()


def test_no_inbox_no_behavior_change() -> None:
    mem = _mem("bottle")
    r = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=ScriptedPlanner(_FETCH),
        executor=MockBody(),
    ).handle("fetch the bottle")
    assert len(r.statuses) == 2
