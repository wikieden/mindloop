"""mindloop error types. Raised only for programmer error / misconfiguration —
expected task failure comes back as a `FAILED` `StatusUpdate` (returns-over-raises).
"""

from __future__ import annotations


class BrainError(Exception):
    """A `Brain` was used in a way its configuration does not support.

    Example: calling `Brain.handle` without the `router`/`planner`/`executor`
    collaborators wired at construction.
    """
