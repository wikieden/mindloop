"""P7.2 — voice seams (Listener/Speaker) + VoiceLoop (network-free, mocks)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    Conversation,
    Listener,
    MockListener,
    MockSpeaker,
    Phylax,
    Policy,
    SafetyContext,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    Speaker,
    TaskStatus,
    VoiceLoop,
    reply_text,
)

DIM = 16


def test_mock_listener_queues_transcripts() -> None:
    lis = MockListener(["hello", "what is here?"])
    assert lis.transcribe(b"...") == "hello"
    assert lis.transcribe(b"...") == "what is here?"
    assert lis.transcribe(b"...") == ""  # past the end -> silence
    assert isinstance(lis, Listener)


def test_mock_speaker_records() -> None:
    sp = MockSpeaker()
    sp.say("hi")
    sp.say("bye")
    assert sp.said == ["hi", "bye"]
    assert isinstance(sp, Speaker)


@pytest.fixture
def brain(tmp_path) -> Brain:
    mem = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)
    rng = np.random.default_rng(0).standard_normal(DIM).astype("float32")
    mem.add_detections(
        [
            Detection(
                "bottle", rng / np.linalg.norm(rng), (1, 0, 0.9), (0.9, -0.1, 0.8), (1.1, 0.1, 1.0)
            )
        ]
    )
    mem.commit()
    return Brain(
        mem,
        ScriptedReasoner({"what is here?": "a bottle [#1]"}),
        router=ScriptedIntentRouter({"what is here?": "question"}, default="task"),
        planner=ScriptedPlanner(
            {
                "bring the bottle": (
                    Command("grasp", ("bottle",)),
                    Command("speak", ("here you go",)),
                )
            }
        ),
        executor=MockBody(),
        policy=Phylax(Policy(adult_only_verbs=frozenset({"grasp"}))),
    )


def test_voice_loop_hears_thinks_speaks(brain: Brain) -> None:
    lis = MockListener(["what is here?", "bring the bottle"])
    sp = MockSpeaker()
    loop = VoiceLoop(brain, lis, sp)
    conv = Conversation()
    adult = SafetyContext(role="adult")

    # turn 1: question -> speaks the cited answer
    r1 = loop.turn(b"audio1", conv, safety_context=adult)
    assert r1.intent == "question"
    assert sp.said[-1] == "a bottle [#1]"

    # turn 2: task -> dispatches + speaks the plan's utterance
    r2 = loop.turn(b"audio2", conv, safety_context=adult)
    assert r2.statuses[-1].status == TaskStatus.SUCCESS
    assert sp.said[-1] == "here you go"
    assert len(conv) == 2  # both turns recorded in the shared conversation


def test_voice_loop_speaks_safety_refusal(brain: Brain) -> None:
    lis = MockListener(["bring the bottle"])
    sp = MockSpeaker()
    loop = VoiceLoop(brain, lis, sp)
    # a child triggers the adult-only gate -> the refusal is spoken, nothing dispatched
    r = loop.turn(b"audio", Conversation(), safety_context=SafetyContext(role="child"))
    assert r.blocked
    assert sp.said and sp.said[-1] == reply_text(r)
    assert r.statuses == ()


def test_voice_loop_ignores_silence(brain: Brain) -> None:
    lis = MockListener([""])  # mis-hear / silence
    sp = MockSpeaker()
    loop = VoiceLoop(brain, lis, sp)
    r = loop.turn(b"noise", Conversation())
    assert sp.said == []  # nothing spoken, nothing dispatched
    assert r.plan is None and r.answer is None
