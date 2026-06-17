"""PreferenceStore — the L5 per-person preference seam (D2).

L5 preferences (taste, habits) overlay skill-card defaults per person. They are
**not** in the memory core (different lifecycle, privacy, per-user isolation,
D2) — a body/deployment supplies an external implementation (e.g. Mem0). This is
a provisional stub: the shape firms up in P5 when skill cards consume it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PreferenceStore(Protocol):
    """Per-person key→value preferences.

    Returns `None` for an unset key (returns-over-raises). Provisional — see the
    module docstring.
    """

    def get(self, person: str, key: str) -> str | None: ...
