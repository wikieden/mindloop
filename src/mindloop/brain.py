"""Brain — the cognitive loop binding memory + reasoning (+ optional perception).

`Brain` ties a `tempomem.SpatialMemory` (the hippocampus) to a `Reasoner` (the
cortex), with an optional `tempomem.PerceptionAdapter` (the eyes, from
`worldsense`). The tick is: perceive → remember (observe/ingest),
then on demand retrieve → reason (ask). See docs/cosmos3-tempomem-llm-brain.md.

v0 is single-threaded; serialize all access (the core store is one sqlite
connection). Active perception (LLM → re-look) is future work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .reason import Answer, Reasoner

if TYPE_CHECKING:
    import numpy as np
    from tempomem import Detection, PerceptionAdapter, SpatialMemory


class Brain:
    """Memory + Reasoner cognitive loop."""

    def __init__(
        self,
        mem: SpatialMemory,
        reasoner: Reasoner,
        *,
        adapter: PerceptionAdapter | None = None,
        max_tokens: int = 1500,
    ) -> None:
        self._mem = mem
        self._reasoner = reasoner
        self._adapter = adapter
        self._budget = max_tokens

    def observe(
        self,
        rgb: np.ndarray,
        depth: np.ndarray,
        pose: np.ndarray,
        *,
        adapter: PerceptionAdapter | None = None,
        episode: str | None = None,
    ) -> Any:
        """Perceive → remember: run a posed frame through perception, then fuse.

        Needs a `PerceptionAdapter` (here or at construction) — perception lives
        in the `worldsense` companion repo. Returns the commit stats.
        """
        self._mem.add_frame(rgb, depth, pose, adapter=adapter or self._adapter, episode=episode)
        return self._mem.commit()

    def ingest(self, detections: list[Detection], *, episode: str | None = None) -> Any:
        """Remember caller-supplied detections (BYO perception), then fuse."""
        self._mem.add_detections(detections, episode=episode)
        return self._mem.commit()

    def ask(self, question: str, *, k: int = 64) -> Answer:
        """Retrieve a query-relevant subgraph → reason → answer.

        Retrieves the top-`k` nodes for `question` and serializes that subgraph —
        the hits, their 1-hop relation neighbours, and the hierarchy ancestors of
        both — within the token budget, rather than dumping the whole scene
        truncated, so the relevant objects survive a tight budget. Falls back to
        the whole scene when nothing matches. `k` is deliberately generous so the
        token budget (not `k`) is the binding limit on a normal scene; an
        enumerative query over more than `k` same-label objects is capped at `k`.
        """
        hits = self._mem.query(question, k=k)
        node_ids = {n.id for n in hits.nodes}
        if node_ids:
            context = self._mem.serialize(
                format="prompt", node_ids=node_ids, max_tokens=self._budget
            )
        else:
            context = self._mem.serialize(format="prompt", max_tokens=self._budget)
        return self._reasoner.reason(question, context)
