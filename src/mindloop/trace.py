"""L4 trace store — episodic memory of attempts + failures (P4, D2/B3).

The brain's *time dimension*: an append-only log of what it tried, what happened,
and why it failed — the fuel for failure-driven replanning (negation learning).
Every record cites tempomem scene-graph **node ids** (the shared id space, B9), so
the trace is queryable by object: "what has failed on node 7?".

Stdlib-only (sqlite3), like tempomem's `.smem`. Append-only by contract: an
episode / failure is **never deleted** (B2R `trace_memory.md` — a trace cannot be
erased; "clearing" a task rotates the `session_id` instead). `:memory:` for tests.

> Scope note (D2): the dev plan envisions this eventually merging into the
> tempomem core for one shared store. For P4 it lives in `mindloop` and cites node
> ids, which already satisfies the shared-id-space requirement; the core merge is
> deferred to a coordinated cross-repo change.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .execute import StatusUpdate, SubTask

_log = logging.getLogger("mindloop.trace")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- 'attempt' | 'failure'
    verb        TEXT NOT NULL,
    subtask_id  TEXT NOT NULL,
    node_ids    TEXT NOT NULL,          -- JSON array of ints
    status      TEXT NOT NULL,
    error_code  TEXT,
    detail      TEXT NOT NULL DEFAULT '',
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
"""


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """One append-only trace row: an attempt or a failure, citing node ids (B9)."""

    id: int
    session_id: str
    kind: str
    verb: str
    subtask_id: str
    node_ids: tuple[int, ...]
    status: str
    error_code: str | None
    detail: str
    ts: float


class TraceStore:
    """Append-only episodic trace of dispatched subtasks + failures (stdlib sqlite)."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

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
        err = status.error_code.value if status.error_code is not None else None
        self._conn.execute(
            "INSERT INTO episodes "
            "(session_id, kind, verb, subtask_id, node_ids, status, error_code, detail, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                session_id,
                kind,
                subtask.verb,
                subtask.id,
                json.dumps(list(subtask.target_node_ids)),
                status.status.value,
                err,
                detail,
                time.time(),
            ),
        )
        self._conn.commit()

    def episodes(self, *, session_id: str | None = None, limit: int = 100) -> list[TraceRecord]:
        """Recent trace records, most recent first; optionally scoped to a session."""
        if session_id is None:
            cur = self._conn.execute("SELECT * FROM episodes ORDER BY id DESC LIMIT ?", (limit,))
        else:
            cur = self._conn.execute(
                "SELECT * FROM episodes WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        return [self._row(r) for r in cur.fetchall()]

    def by_node(self, node_id: int, *, limit: int = 100) -> list[TraceRecord]:
        """Every record that touched `node_id` (queryable by object — B9 audit)."""
        rows = self._conn.execute(
            "SELECT * FROM episodes ORDER BY id DESC LIMIT ?", (limit * 4,)
        ).fetchall()
        out = [self._row(r) for r in rows]
        return [r for r in out if node_id in r.node_ids][:limit]

    def failures(self, *, session_id: str | None = None) -> list[TraceRecord]:
        """Just the failure records (the negation-learning view)."""
        return [r for r in self.episodes(session_id=session_id, limit=1000) if r.kind == "failure"]

    @staticmethod
    def _row(r: tuple) -> TraceRecord:
        return TraceRecord(
            id=r[0],
            session_id=r[1],
            kind=r[2],
            verb=r[3],
            subtask_id=r[4],
            node_ids=tuple(json.loads(r[5])),
            status=r[6],
            error_code=r[7],
            detail=r[8],
            ts=r[9],
        )

    def close(self) -> None:
        self._conn.close()
