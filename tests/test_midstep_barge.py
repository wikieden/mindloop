"""T5-8 — mid-step barge-in (D-E full closure).

The dispatch loop now polls the interrupt inbox BETWEEN stream updates of an
in-flight step, not only at step boundaries: an abort/supersede/correction
cancels the step through the body's cancel handshake and hands the utterance
to the existing boundary machinery; chitchat is answered inline while the step
keeps running. A body without the handshake falls back to the D-E baseline
(queued to the boundary) — never dropped.
"""

from __future__ import annotations

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    MockSpeaker,
    QueueInterruptSource,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    TraceStore,
)


def _mem() -> TempoMem:
    mem = TempoMem.open(":memory:", embedding_dim=4)
    v = np.ones(4, dtype="float32") / 2.0
    mem.add_detections([Detection("mug", v, (0.5, 0.5, 0.8), (0.4, 0.4, 0.7), (0.6, 0.6, 0.9))])
    mem.commit()
    return mem


class _PushDuringStep(MockBody):
    """Pushes one utterance into the inbox as the FIRST step starts executing."""

    def __init__(self, inbox: QueueInterruptSource, utterance: str) -> None:
        super().__init__()
        self._inbox = inbox
        self._utt = utterance
        self._pushed = False

    def dispatch(self, subtask):
        if not self._pushed:
            self._pushed = True
            self._inbox.push(self._utt)
        yield from super().dispatch(subtask)


class _NoHandshake:
    """A minimal body WITHOUT cancel/pause/resume — D-E baseline behavior."""

    def __init__(self, inbox: QueueInterruptSource, utterance: str) -> None:
        self._inner = _PushDuringStep(inbox, utterance)

    def capabilities(self):
        return self._inner.capabilities()

    def dispatch(self, subtask):
        return self._inner.dispatch(subtask)


_PLANS = {
    "bring the mug": (Command("navigate", ("mug",)), Command("grasp", ("mug",))),
    "go to the charger instead": (Command("charging", ()),),
}


def _brain(body, inbox, *, intents=None, trace=None, speaker=None) -> Brain:
    return Brain(
        _mem(),
        ScriptedReasoner({"nice house!": "thank you! [#1]"}),
        router=ScriptedIntentRouter(intents or {}, default="task"),
        planner=ScriptedPlanner(_PLANS),
        executor=body,
        interrupts=inbox,
        speaker=speaker,
        trace=trace,
    )


def test_midstep_stop_cancels_the_inflight_step() -> None:
    inbox = QueueInterruptSource()
    speaker = MockSpeaker()
    r = _brain(_PushDuringStep(inbox, "stop"), inbox, speaker=speaker).handle("bring the mug")
    # the in-flight navigate was cancelled, the second step never dispatched
    assert len(r.statuses) == 1
    assert r.statuses[0].status.value == "aborted"
    assert any("stopping" in s.lower() for s in speaker.said)


def test_midstep_chitchat_answers_inline_and_step_completes() -> None:
    inbox = QueueInterruptSource()
    speaker = MockSpeaker()
    r = _brain(
        _PushDuringStep(inbox, "nice house!"),
        inbox,
        intents={"nice house!": "chat"},
        speaker=speaker,
    ).handle("bring the mug")
    assert [st.status.value for st in r.statuses] == ["success", "success"]
    assert any("thank you" in s for s in speaker.said)


def test_midstep_supersede_cancels_then_replans_at_boundary() -> None:
    inbox = QueueInterruptSource()
    tr = TraceStore(":memory:")
    r = _brain(
        _PushDuringStep(inbox, "go to the charger instead"), inbox, trace=tr
    ).handle("bring the mug")
    # navigate aborted mid-step, then the superseding goal ran to success
    assert r.statuses[0].status.value == "aborted"
    assert r.statuses[-1].status.value == "success"
    verbs = [rec.verb for rec in reversed(tr.episodes(limit=100))]
    assert "charging" in verbs and "grasp" not in verbs
    tr.close()


def test_body_without_handshake_defers_to_boundary() -> None:
    inbox = QueueInterruptSource()
    tr = TraceStore(":memory:")
    r = _brain(
        _NoHandshake(inbox, "go to the charger instead"), inbox, trace=tr
    ).handle("bring the mug")
    # no cancel available: the step finishes (D-E baseline), the barge is
    # handled at the boundary — deferred, never dropped
    assert r.statuses[0].status.value == "success"
    assert r.statuses[-1].status.value == "success"
    verbs = [rec.verb for rec in reversed(tr.episodes(limit=100))]
    assert "charging" in verbs and "grasp" not in verbs
    tr.close()
