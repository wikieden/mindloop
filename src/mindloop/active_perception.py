"""Active perception — re-look between steps to keep the plan grounded (dynamic-scene P4).

During a multi-step task the world moves: an object is taken, a door swings, the
robot's own viewpoint changes. `ActivePerception` is the seam that decides **when to
re-perceive** and supplies the fresh `Detection`s to fuse. The brain calls it between
dispatched steps; new detections update the map (a version bump), which can make the
plan tail stale → a bounded re-plan with fresh context (dynamic-scene §2b trigger 3/4).

BYO, like the other seams: mindloop ships the protocol + a `ScriptedPerception`
double (network-free); a real body fills it with `worldsense` (camera → detections).
A `None`/empty return means "nothing new to see" — no re-plan, dispatch continues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from tempomem import Detection

    from .execute import StatusUpdate


@runtime_checkable
class ActivePerception(Protocol):
    """Decides whether to re-look before a step and returns the detections to fuse."""

    def perceive(
        self, *, step_index: int, last_status: StatusUpdate | None
    ) -> list[Detection] | None: ...


class ScriptedPerception:
    """A deterministic `ActivePerception` for tests: step index → detections, once.

    `relooks` maps a 0-based step index to the `Detection`s that "appear" just before
    that step. Each entry fires at most once (so a re-plan that restarts the loop
    doesn't re-trigger the same observation). Other steps see nothing.
    """

    def __init__(self, relooks: dict[int, list[Detection]] | None = None) -> None:
        self._relooks = dict(relooks or {})
        self._fired: set[int] = set()

    def perceive(
        self, *, step_index: int, last_status: StatusUpdate | None
    ) -> list[Detection] | None:
        if step_index in self._relooks and step_index not in self._fired:
            self._fired.add(step_index)
            return self._relooks[step_index]
        return None
