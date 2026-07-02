"""Scene-context provider — the read-path seam for inference context (dynamic-scene P1).

The brain hands the LLM a serialized slice of the tempomem semantic map as context.
Today that read path (`query` → `serialize`) is inlined in `Brain.ask` /
`Brain._plan_context`; this factors it into a seam so the *when* and *how much* of
context can evolve (active perception, version-gated re-query) without touching the
brain's orchestration. See docs/research/dynamic-scene-context.md.

**Phase 1 is behavior-preserving:** `DefaultSceneContextProvider` wraps exactly the
existing `query` + `serialize` calls and returns the same context string, plus a
**map version** (`int`) for the caller to gate re-serialization later. The version
is plumbing here — it advances only when `bump()` is called (the brain does so on
`observe`/`ingest`); real change-detection at the node level is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from tempomem import TempoMem


@dataclass(frozen=True, slots=True)
class Focus:
    """What the context should be *about* — the retrieval intent + things to keep in view.

    `query` is the instruction/question that routes retrieval. `node_ids` are plan
    targets the caller wants kept in the serialized subgraph even if the query
    wouldn't surface them (used once execution threads the plan's targets through —
    empty today, so behavior is unchanged). `region` is the robot's current region
    (reserved for region-aware context).
    """

    query: str
    node_ids: tuple[int, ...] = ()
    region: str | None = None


@runtime_checkable
class SceneContextProvider(Protocol):
    """Builds the serialized scene context for a `Focus`, with a map version."""

    def context(
        self, focus: Focus, *, k: int = 64, max_tokens: int | None = None
    ) -> tuple[str, int]: ...


class DefaultSceneContextProvider:
    """Behavior-preserving provider: today's `query` + `serialize`, plus a version.

    Returns the same context string `Brain.ask`/`_plan_context` produced inline —
    the top-`k` query hits (unioned with any `focus.node_ids`) serialized as a
    token-budgeted subgraph, falling back to the whole scene when nothing matches.
    The second tuple element is the current map `version`.
    """

    def __init__(self, mem: TempoMem, *, default_budget: int = 1500) -> None:
        self._mem = mem
        self._budget = default_budget
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def bump(self) -> int:
        """Advance the map version (the brain calls this after a perception write)."""
        self._version += 1
        return self._version

    def context(
        self, focus: Focus, *, k: int = 64, max_tokens: int | None = None
    ) -> tuple[str, int]:
        budget = max_tokens if max_tokens is not None else self._budget
        hits = self._mem.query(focus.query, k=k)
        node_ids = {n.id for n in hits.nodes} | set(focus.node_ids)
        if node_ids:
            text = self._mem.serialize(format="prompt", node_ids=node_ids, max_tokens=budget)
        else:
            text = self._mem.serialize(format="prompt", max_tokens=budget)
        return text, self._version
