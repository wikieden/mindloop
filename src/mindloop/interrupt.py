"""Barge-in seam — interrupt inbox + classifier (3b, TASK-FAMILIES §7b.1 / D2).

A human speaking *during* a running task must change what the robot does — not
be ignored until the plan finishes. Two pieces, both brain-side and stdlib-only:

* `InterruptSource` — a **non-blocking inbox** the dispatch loop polls between
  steps (D-E: between-step precision; mid-step preemption needs a bodylink
  cancel/pause/resume handshake and is deferred to P4). The baseline
  `QueueInterruptSource` is scripted/test-friendly; a voice deployment feeds the
  same seam from a streaming-ASR callback.
* `BargeClassifier` (D2) — decides what the utterance does **to the running
  task**: chitchat/question → answer inline and resume; a new instruction →
  supersede; a correction → re-plan the same goal with the fix; stop → abort.
  This is a *different decision space* from the 3-way `Intent`, so it composes
  the existing `IntentRouter` rather than adding a 4th literal.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .plan import IntentRouter

BargeKind = Literal["answer_resume", "supersede", "correction", "abort"]

# Conservative default stop lexicon (exact match after strip/casefold). A voice
# deployment may pass a wider set; matching stays exact-token to avoid "stop at
# the kitchen" false positives.
_STOP_WORDS: frozenset[str] = frozenset({"stop", "stop!", "cancel", "halt", "停", "停下", "取消"})

# A correction rephrases the *same* goal ("no, the red one") — checked before
# intent routing because a correction often parses as a task on its own.
_CORRECTION_MARKERS: tuple[str, ...] = ("no,", "no ", "not that", "不对", "不是", "错了")


@runtime_checkable
class InterruptSource(Protocol):
    """Non-blocking inbox of human utterances arriving mid-task."""

    def poll(self) -> str | None:
        """The next pending utterance, or None when the inbox is empty."""
        ...


class QueueInterruptSource:
    """FIFO `InterruptSource` — scripted for tests, push-fed in a deployment."""

    def __init__(self, utterances: Iterable[str] = ()) -> None:
        self._q: deque[str] = deque(utterances)

    def push(self, utterance: str) -> None:
        self._q.append(utterance)

    def poll(self) -> str | None:
        return self._q.popleft() if self._q else None


@dataclass(frozen=True, slots=True)
class BargeDecision:
    """What a barge-in does to the running task, plus the utterance itself."""

    kind: BargeKind
    utterance: str


class BargeClassifier:
    """Classify a mid-task utterance into a `BargeDecision` (D2).

    Order matters: stop words are checked first (safety), then correction
    markers (a correction usually *looks* like a task), then the composed
    `IntentRouter` splits answer-and-resume (question/chat) from supersede (task).
    """

    def __init__(
        self,
        router: IntentRouter,
        *,
        stop_words: frozenset[str] = _STOP_WORDS,
        correction_markers: tuple[str, ...] = _CORRECTION_MARKERS,
    ) -> None:
        self._router = router
        self._stop = {w.casefold() for w in stop_words}
        self._corrections = correction_markers

    def classify(self, utterance: str) -> BargeDecision:
        low = utterance.strip().casefold()
        if low in self._stop:
            return BargeDecision("abort", utterance)
        if any(low.startswith(m) for m in self._corrections):
            return BargeDecision("correction", utterance)
        intent = self._router.classify(utterance)
        if intent in ("question", "chat"):
            return BargeDecision("answer_resume", utterance)
        return BargeDecision("supersede", utterance)
