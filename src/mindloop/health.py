"""Brain health-check (B5) — mirrors the body team's L3 init checklist.

The body's bring-up probes `llm_model` / `world_model` / `task_library`; the
brain answers with the same readiness picture so a body can gate on it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Brain readiness.

    `reasoner_ready` ↔ their `llm_model`, `memory_ready` ↔ `world_model`.
    `skill_library_ready` ↔ `task_library` and stays `None` until the Episteme
    card library lands (P2). `ok` is true when every required faculty is ready.
    """

    reasoner_ready: bool
    memory_ready: bool
    skill_library_ready: bool | None = None

    @property
    def ok(self) -> bool:
        """True when the reasoner and memory are both ready."""
        return self.reasoner_ready and self.memory_ready
