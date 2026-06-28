"""World-state overlay — symbolic effect write-back (dynamic-scene P2).

A fast symbolic layer on top of the perceptual map: `predicate → value` facts the
brain *knows* from completed actions, even before a camera confirms them. When a
`SubTask` succeeds, its `effects` (already concrete strings from the compiler, e.g.
``robot.holding=apple``, ``fridge.status=open``) are written here; the current
facts are injected into the inference context so a multi-step task stays grounded
**without re-perceiving every step** (the cheap half of the dynamic-scene loop —
see docs/research/dynamic-scene-context.md §2a).

Two layers, deliberately separate: the **perceptual map** (tempomem) is the slow
ground truth; this **symbolic overlay** (mindloop, no tempomem-core change) is the
fast prediction. Active perception (a later phase) reconciles the two when the
prediction is uncertain. Stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Effect:
    """A parsed effect predicate: ``key=value`` (e.g. ``robot.holding`` = ``apple``)."""

    key: str
    value: str


def parse_effect(s: str) -> Effect | None:
    """Parse a ``key=value`` effect string; return None if it isn't one."""
    if "=" not in s:
        return None
    k, _, v = s.partition("=")
    k, v = k.strip(), v.strip()
    return Effect(k, v) if k else None


@runtime_checkable
class EffectApplier(Protocol):
    """Applies confirmed `SubTask` effects; returns the new state version."""

    def apply(self, effects: tuple[str, ...]) -> int: ...


class WorldState:
    """Symbolic `predicate → value` overlay, updated by confirmed effects (P2).

    `apply` writes effects (latest value wins per key) and bumps `version` when
    anything changed. `render` is the context block the brain injects; `reset`
    starts a fresh task (the robot's running state cleared). Persists across
    `handle` calls within one brain — that *is* the robot's state.
    """

    def __init__(self) -> None:
        self._state: dict[str, str] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def apply(self, effects: tuple[str, ...]) -> int:
        changed = False
        for s in effects:
            e = parse_effect(s)
            if e is None:
                continue
            if self._state.get(e.key) != e.value:
                self._state[e.key] = e.value
                changed = True
        if changed:
            self._version += 1
        return self._version

    def get(self, key: str) -> str | None:
        return self._state.get(key)

    def snapshot(self) -> dict[str, str]:
        return dict(self._state)

    def reset(self) -> None:
        """Clear the overlay (a new task / a re-perception override)."""
        if self._state:
            self._state.clear()
            self._version += 1

    def render(self) -> str:
        """The context block of current facts (empty string when there are none)."""
        if not self._state:
            return ""
        lines = "\n".join(f"{k}={v}" for k, v in sorted(self._state.items()))
        return f"WORLD STATE (facts from completed actions):\n{lines}"
