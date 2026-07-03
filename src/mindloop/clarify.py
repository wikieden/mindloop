"""Clarifier — the brain-level ask-human seam (3b, TASK-FAMILIES D3).

Robot-initiated questioning, distinct from human-initiated barge-in: when the
brain is genuinely stuck (a dead-end ESCALATE whose goal is still reachable
with more information), it asks a *targeted* question and folds the answer back
into planning instead of giving up.

Discipline (ratified): the ask budget is **≤2 per task, reset per task** (no
conversation-level cap — asking about a previous task must not starve a later
one); exceeding it stops honestly. A clarification answer **is an instruction**
— the caller re-vets the resulting plan through Phylax, so a stranger cannot
unlock a blocked action via a clarification reply.

A voice deployment implements the protocol over `Speaker.say` + a listener
turn; the baseline `ScriptedClarifier` keeps tests deterministic + network-free.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clarifier(Protocol):
    """Ask the human one targeted question; None means no usable answer."""

    def clarify(self, question: str) -> str | None: ...


class ScriptedClarifier:
    """Deterministic `Clarifier` for tests: substring-matched answers + default.

    Every question asked is recorded in `asked` so tests can assert on the ask
    budget and on don't-over-ask behavior.
    """

    def __init__(
        self, answers: Mapping[str, str] | None = None, *, default: str | None = None
    ) -> None:
        self._answers = dict(answers or {})
        self._default = default
        self.asked: list[str] = []

    def clarify(self, question: str) -> str | None:
        self.asked.append(question)
        for needle, answer in self._answers.items():
            if needle in question:
                return answer
        return self._default
