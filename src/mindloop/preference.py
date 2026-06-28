"""PreferenceStore — the L5 per-person preference seam (D2).

L5 preferences (taste, habits) overlay skill-card defaults per person. They are
**not** in the memory core (different lifecycle, privacy, per-user isolation,
D2) — a body/deployment supplies an external implementation (e.g. Mem0). The brain
overlays a person's preferences onto a compiled plan's params at plan time (P5),
gated to the verb's declared params so a preference cannot inject an unknown key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping


@runtime_checkable
class PreferenceStore(Protocol):
    """Per-person key→value preferences.

    `get` returns `None` for an unset key (returns-over-raises); `all` returns a
    person's full preference map (empty if none) — the brain reads `all` to overlay
    a plan.
    """

    def get(self, person: str, key: str) -> str | None: ...

    def all(self, person: str) -> Mapping[str, str]: ...


class DictPreferenceStore:
    """An in-memory `PreferenceStore` — `{person: {key: value}}`.

    The reference fill for tests and simple deployments; a real backend (Mem0,
    a per-user DB) implements the same protocol and stays external (D2).
    """

    def __init__(self, prefs: Mapping[str, Mapping[str, str]] | None = None) -> None:
        self._prefs: dict[str, dict[str, str]] = {
            person: dict(kv) for person, kv in (prefs or {}).items()
        }

    def set(self, person: str, key: str, value: str) -> None:
        """Set one preference for `person`."""
        self._prefs.setdefault(person, {})[key] = value

    def get(self, person: str, key: str) -> str | None:
        return self._prefs.get(person, {}).get(key)

    def all(self, person: str) -> Mapping[str, str]:
        return dict(self._prefs.get(person, {}))
