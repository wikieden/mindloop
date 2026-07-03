"""3b slice 1 — InterruptSource inbox + BargeClassifier (D2, TASK-FAMILIES §7b.1).

The classifier decides what a mid-task human utterance does to the RUNNING task
(answer+resume / supersede / correction / abort) — a different decision space
from the 3-way Intent, so it composes the IntentRouter rather than extending it.
"""

from __future__ import annotations

from mindloop import (
    BargeClassifier,
    QueueInterruptSource,
    ScriptedIntentRouter,
)


def _clf() -> BargeClassifier:
    router = ScriptedIntentRouter(
        {
            "what year was this built?": "question",
            "nice weather today": "chat",
            "bring me the mug": "task",
        },
        default="task",
    )
    return BargeClassifier(router)


# --------------------------------------------------------------------------- #
# inbox
# --------------------------------------------------------------------------- #
def test_queue_source_polls_fifo_then_empty() -> None:
    src = QueueInterruptSource(["a", "b"])
    assert src.poll() == "a"
    assert src.poll() == "b"
    assert src.poll() is None


def test_queue_source_push_mid_run() -> None:
    src = QueueInterruptSource()
    assert src.poll() is None
    src.push("stop")
    assert src.poll() == "stop"


# --------------------------------------------------------------------------- #
# classification (D2 4-way)
# --------------------------------------------------------------------------- #
def test_stop_words_abort() -> None:
    clf = _clf()
    for utt in ("stop", "Stop!", "cancel", "停", "停下", "取消"):
        assert clf.classify(utt).kind == "abort", utt


def test_question_and_chat_answer_then_resume() -> None:
    clf = _clf()
    assert clf.classify("what year was this built?").kind == "answer_resume"
    assert clf.classify("nice weather today").kind == "answer_resume"


def test_new_instruction_supersedes() -> None:
    assert _clf().classify("bring me the mug").kind == "supersede"


def test_correction_markers_win_over_task_intent() -> None:
    clf = _clf()
    assert clf.classify("no, the red one").kind == "correction"
    assert clf.classify("不对，是红色那个").kind == "correction"  # noqa: RUF001


def test_decision_carries_the_utterance() -> None:
    d = _clf().classify("bring me the mug")
    assert d.utterance == "bring me the mug"
