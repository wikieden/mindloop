"""Dialogue — multi-turn conversation state for the S2 loop (P5).

A `Conversation` carries the turn history so a question/chat turn can be answered
with the recent turns as context (a follow-up like "the other one" resolves against
the prior turn). It is a thin wrapper over `Brain.handle`: the single-turn loop is
unchanged; `Brain.converse` threads the history into `ask` and appends each turn.
Memory-grounded *and* dialogue-grounded — the scene graph answers *what's there*,
the conversation answers *what we were just talking about*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plan import HandleResult


@dataclass(frozen=True, slots=True)
class Turn:
    """One conversational turn: the user instruction + the brain's outcome."""

    instruction: str
    result: HandleResult


class Conversation:
    """Ordered turn history for a multi-turn session."""

    def __init__(self) -> None:
        self._turns: list[Turn] = []

    @property
    def turns(self) -> tuple[Turn, ...]:
        return tuple(self._turns)

    def __len__(self) -> int:
        return len(self._turns)

    def add(self, instruction: str, result: HandleResult) -> None:
        """Append a completed turn."""
        self._turns.append(Turn(instruction, result))

    def history_text(self, n: int = 3) -> str:
        """Render the recent `n` turns as ``User:``/``Assistant:`` lines for context.

        The assistant line is the turn's spoken reply — an `Answer.text` for a
        question/chat, or the `Plan.speak` for a task. Turns with no reply are shown
        as the user line only.
        """
        lines: list[str] = []
        for t in self._turns[-n:]:
            lines.append(f"User: {t.instruction}")
            reply = ""
            if t.result.answer is not None:
                reply = t.result.answer.text
            elif t.result.plan is not None:
                reply = t.result.plan.speak
            if reply:
                lines.append(f"Assistant: {reply}")
        return "\n".join(lines)
