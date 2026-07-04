"""P7.3 seam — `ListenerInterruptSource`: voice-fed barge-in.

Bridges the two existing seams: pending mic audio (a non-blocking
`audio_source`) is transcribed by a `Listener` and lands in the same
`InterruptSource` inbox the dispatch loop already polls between steps. Fully
network-free here; a real deployment fills `audio_source` from streaming
ASR+VAD on the body (deferred, hardware).
"""

from __future__ import annotations

from collections import deque

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    ListenerInterruptSource,
    MockListener,
    MockSpeaker,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
)


def _chunks(*items: bytes):
    q = deque(items)
    return lambda: q.popleft() if q else None


def test_no_pending_audio_is_silence() -> None:
    src = ListenerInterruptSource(MockListener(["hello"]), audio_source=lambda: None)
    assert src.poll() is None


def test_pending_audio_is_transcribed_once() -> None:
    src = ListenerInterruptSource(MockListener(["stop"]), audio_source=_chunks(b"a"))
    assert src.poll() == "stop"
    assert src.poll() is None  # chunk consumed


def test_blank_transcript_is_swallowed() -> None:
    # a misheard nothing must never become a barge-in
    src = ListenerInterruptSource(MockListener([""]), audio_source=_chunks(b"noise"))
    assert src.poll() is None


def test_voice_stop_aborts_the_running_task() -> None:
    mem = TempoMem.open(":memory:", embedding_dim=4)
    v = np.ones(4, dtype="float32") / 2.0
    mem.add_detections([Detection("mug", v, (0.5, 0.5, 0.8), (0.4, 0.4, 0.7), (0.6, 0.6, 0.9))])
    mem.commit()
    speaker = MockSpeaker()
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=ScriptedPlanner(
            {"bring the mug": (Command("navigate", ("mug",)), Command("grasp", ("mug",)))}
        ),
        executor=MockBody(),
        interrupts=ListenerInterruptSource(MockListener(["stop"]), audio_source=_chunks(b"a")),
        speaker=speaker,
    )
    r = brain.handle("bring the mug")
    assert r.statuses == ()  # aborted before the first step dispatched
    assert any("stopping" in s.lower() for s in speaker.said)
