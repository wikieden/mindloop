"""L4 trace store — episodic memory of attempts + failures (P4, D2/B3).

D2 landed (T5-9): the storage engine now lives in the **tempomem core**
(`tempomem.trace.TraceLog` — one shared store/id space, optionally inside the
`.smem` itself via `TempoMem.trace_log()`). This module is the brain-side
adapter: it keeps the P4 `TraceStore` API (typed `SubTask`/`StatusUpdate` in,
`TraceRecord` out) and translates to the core's primitive `record()` — the
core never imports brain types.

Append-only by contract: an episode / failure is **never deleted** (B2R
`trace_memory.md`); "clearing" a task rotates the `session_id`. `:memory:` for
tests. Pre-D2 standalone trace files are adopted in place by the core's
legacy migration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tempomem.trace import TraceLog, TraceRecord

if TYPE_CHECKING:
    from .execute import StatusUpdate, SubTask

__all__ = ["TraceRecord", "TraceStore"]


class TraceStore:
    """Append-only episodic trace of dispatched subtasks + failures.

    A thin brain-side adapter over `tempomem.trace.TraceLog` (D2). Constructed
    from a `path` (own sqlite file / ``":memory:"``) or from an existing core
    `TraceLog` (e.g. ``TraceStore(log=mem.trace_log())`` to share the `.smem`).
    """

    def __init__(self, path: str = ":memory:", *, log: TraceLog | None = None) -> None:
        self._log = log if log is not None else TraceLog(path)

    def log_attempt(
        self, subtask: SubTask, status: StatusUpdate, *, session_id: str = "default"
    ) -> None:
        """Record a dispatched subtask's terminal outcome (attempt or failure)."""
        kind = "failure" if status.status.value == "failed" else "attempt"
        self._insert(kind, subtask, status, session_id, detail=status.message)

    def log_failure(
        self,
        subtask: SubTask,
        status: StatusUpdate,
        *,
        session_id: str = "default",
        detail: str = "",
    ) -> None:
        """Record a failure explicitly (negation-learning fuel; never deleted)."""
        self._insert("failure", subtask, status, session_id, detail=detail or status.message)

    def _insert(
        self, kind: str, subtask: SubTask, status: StatusUpdate, session_id: str, *, detail: str
    ) -> None:
        self._log.record(
            session_id=session_id,
            kind=kind,
            verb=subtask.verb,
            subtask_id=subtask.id,
            node_ids=subtask.target_node_ids,
            status=status.status.value,
            error_code=status.error_code.value if status.error_code is not None else None,
            detail=detail,
            macro_parent=subtask.macro_parent,
        )

    def episodes(self, *, session_id: str | None = None, limit: int = 100) -> list[TraceRecord]:
        """Recent trace records, most recent first; optionally scoped to a session."""
        return self._log.episodes(session_id=session_id, limit=limit)

    def by_node(self, node_id: int, *, limit: int = 100) -> list[TraceRecord]:
        """Every record that touched `node_id` (queryable by object — B9 audit)."""
        return self._log.by_node(node_id, limit=limit)

    def failures(self, *, session_id: str | None = None) -> list[TraceRecord]:
        """Just the failure records (the negation-learning view)."""
        return self._log.failures(session_id=session_id)

    def close(self) -> None:
        self._log.close()
