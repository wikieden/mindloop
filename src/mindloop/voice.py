"""Voice I/O seams — the ears (ASR) and mouth (TTS) of the offline AI chain (P7.2).

The brain reasons over text; speech is two BYO seams, the same pattern as
`ExecutorAdapter`/`Verbalizer`: mindloop ships the **protocols** (`Listener`,
`Speaker`) and `Mock*` doubles, while real on-body engines (whisper.cpp /
sherpa-onnx for ASR; piper / Qwen3-TTS for TTS) live out-of-tree behind the device
package (P7.3). `VoiceLoop` ties them to `Brain.converse`: hear → think → speak.

Network-free: audio is opaque `bytes` here; the mocks ignore the bytes and script
the transcript / record the utterances, so the whole voice loop is testable with no
audio stack. Realizes the recommended D-edge-2 design (new BYO speech seams) — the
seams are additive/reversible; the owner ratification of D-edge-2 stands open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from .brain import Brain
    from .dialogue import Conversation
    from .phylax import SafetyContext
    from .plan import HandleResult


@runtime_checkable
class Listener(Protocol):
    """ASR seam (the ears): decode audio to a text instruction."""

    def transcribe(self, audio: bytes) -> str: ...


@runtime_checkable
class Speaker(Protocol):
    """TTS seam (the mouth): utter a line of text."""

    def say(self, text: str) -> None: ...


class MockListener:
    """A scripted `Listener` — returns queued transcripts in order, ignoring audio.

    `transcribe` pops the next scripted line; past the end it returns `""` (silence).
    """

    def __init__(self, transcripts: list[str] | None = None) -> None:
        self._queue = list(transcripts or [])
        self._i = 0

    def transcribe(self, audio: bytes) -> str:
        if self._i >= len(self._queue):
            return ""
        text = self._queue[self._i]
        self._i += 1
        return text


class MockSpeaker:
    """A `Speaker` that records what it was asked to say (for tests/telemetry)."""

    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text: str) -> None:
        self.said.append(text)


class ListenerInterruptSource:
    """Voice-fed `InterruptSource` (P7.3 seam): pending audio → transcript → inbox.

    Bridges the ears to the barge-in inbox: ``audio_source`` is the non-blocking
    mic/VAD seam (return the next captured utterance chunk, or None when nothing
    new); `poll` transcribes at most one chunk per call through the `Listener`.
    A blank transcript is swallowed — a misheard nothing never becomes a barge.
    On-body streaming ASR+VAD fills ``audio_source`` (deferred, hardware);
    tests script it.
    """

    def __init__(self, listener: Listener, *, audio_source: Callable[[], bytes | None]) -> None:
        self._listener = listener
        self._audio = audio_source

    def poll(self) -> str | None:
        chunk = self._audio()
        if not chunk:
            return None
        text = self._listener.transcribe(chunk).strip()
        return text or None


def reply_text(result: HandleResult) -> str:
    """The line to speak for a turn: the `Answer` text, else the plan's `speak`."""
    if result.answer is not None:
        return result.answer.text
    if result.plan is not None:
        return result.plan.speak
    return ""


class VoiceLoop:
    """Hear → think → speak: ties a `Listener` + `Speaker` to `Brain.converse` (P7.2).

    One turn = transcribe audio → run the brain (dialogue-grounded via the shared
    `Conversation`) → speak the reply. The brain is unchanged; this is the thin
    voice wrapper. With an on-body `Listener`/`Speaker` + a `FailoverVerbalizer`
    reasoner, the whole loop runs offline (the P7 goal).
    """

    def __init__(self, brain: Brain, listener: Listener, speaker: Speaker) -> None:
        self._brain = brain
        self._listener = listener
        self._speaker = speaker

    def turn(
        self,
        audio: bytes,
        conversation: Conversation,
        *,
        person: str = "",
        safety_context: SafetyContext | None = None,
    ) -> HandleResult:
        """Run one spoken turn; returns the `HandleResult` (and speaks the reply).

        A silent transcription (`""`) is a no-op that speaks nothing and is **not**
        dispatched — the brain never acts on a misheard nothing.
        """
        text = self._listener.transcribe(audio).strip()
        if not text:
            from .plan import HandleResult as _HR

            return _HR(intent="chat")
        result = self._brain.converse(
            text, conversation, person=person, safety_context=safety_context
        )
        reply = reply_text(result)
        if reply:
            self._speaker.say(reply)
        return result
