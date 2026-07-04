"""The executor seam — what the brain dispatches to a body, and reads back.

This is the D1/D3 execution contract. The brain (S2) owns these value types and
the `ExecutorAdapter` protocol; a body package (`bodylink`, or a real device
package) *fills* the protocol — the same pattern as `Reasoner`, where the caller
owns the contract. The brain plans in **skill verbs** and dispatches `SubTask`s
carrying tempomem scene-graph **node ids** (B9 — the audit chain from memory to
actuator stays closed); it never speaks joint space or base-frame geometry
(D3/B8 — that lives below L2). Errors and recovery hints are **typed**, never
free text (B3). The `CapabilityManifest` is **two-tier** (D3): a verb tier the
planner reads + a Body Profile tier the executor uses — a new robot ships a new
manifest and the brain changes nothing.

Value types are immutable (`frozen=True, slots=True`) per
tempomem/spec/ENGINEERING.md. Stdlib-only.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class TaskStatus(str, Enum):
    """Lifecycle of a dispatched `SubTask` (mirrors the body team's TaskStatus)."""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    ABORTED = "aborted"

    @property
    def is_terminal(self) -> bool:
        """True once no further updates will follow for this subtask."""
        return self in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.ABORTED)


class ErrorCode(str, Enum):
    """Typed executor error codes (B3) — a closed contract; bodies map their
    faults onto these, never free text.

    The task-level codes (`GRASP_FAILED`, `OBJECT_LOST`) and `BATTERY_LOW` are
    the ones that rise to the brain for replanning (P4); the rest are handled at
    L1/L2 and reported only for the L4 trace.
    """

    COLLISION = "ERR_COLLISION"
    JOINT_LIMIT = "ERR_JOINT_LIMIT"
    TORQUE_OVR = "ERR_TORQUE_OVR"
    CAN_DISCONNECT = "ERR_CAN_DISCONNECT"
    IK_NO_SOLUTION = "ERR_IK_NO_SOLUTION"
    TRAJECTORY_TRACKING = "ERR_TRAJECTORY_TRACKING"
    NAV_OBSTACLE = "ERR_NAV_OBSTACLE"
    GRASP_FAILED = "ERR_GRASP_FAILED"
    OBJECT_LOST = "ERR_OBJECT_LOST"
    BATTERY_LOW = "ERR_BATTERY_LOW"
    COMM_LOST = "ERR_COMM_LOST"
    SENSOR_FAIL = "ERR_SENSOR_FAIL"


class RecoveryKind(str, Enum):
    """Typed recovery-adjustment vocabulary (B3) the brain may apply on replan."""

    POSITION_OFFSET = "position_offset"
    ORIENTATION_RELAX = "orientation_relax"
    FORCE_ADJUSTMENT = "force_adjustment"
    RETRY = "retry"
    SKIP = "skip"
    REPLAN = "replan"


@dataclass(frozen=True, slots=True)
class RecoveryHint:
    """A typed suggestion a body returns with a failure, for the brain's replan.

    `value` is the magnitude where one applies (meters for `POSITION_OFFSET`,
    radians for `ORIENTATION_RELAX`, a 0..1 fraction for `FORCE_ADJUSTMENT`);
    `None` for kinds that take no magnitude (`RETRY` / `SKIP` / `REPLAN`).
    """

    kind: RecoveryKind
    value: float | None = None


@dataclass(frozen=True, slots=True)
class SubTask:
    """One skill-verb step the brain dispatches to a body.

    `verb` is an open-vocabulary skill verb (e.g. ``"navigate"``, ``"grasp"``),
    validated against the body's `CapabilityManifest` at plan time rather than a
    fixed enum (a new body adds verbs without a brain change, D3).
    `target_node_ids` are tempomem scene-graph node ids the verb acts on (B9);
    the body echoes them back in its `StatusUpdate` so the audit chain stays
    closed. `params` carries verb-specific arguments at the category/affordance
    level — **no** joint angles or base-frame poses (those live below L2, D3/B8).
    """

    id: str
    verb: str
    target_node_ids: tuple[int, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    # B2R-MVP-aligned metadata, filled by the deterministic planner compiler
    # (`plan.compile_commands`). The brain *carries* but does **not** enforce
    # `preconditions`/`effects` — the symbolic-BT tier in `bodylink` does (D4).
    # `skill` is the executor-side implementation hint; `timeout_s` bounds the
    # dispatch. See plan.py and B2R `subtask_compiler.py`.
    skill: str = ""
    preconditions: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    timeout_s: float = 30.0
    # D-C (minimal): positional args keyed by the manifest verb's declared param
    # names ({"liquid": "water", "container": "cup"}) so a policy gate can inspect
    # the *right* argument (region-access, allergen target) without positional
    # guessing. Filled by the compiler from `VerbSpec.params`.
    named_params: dict[str, str] = field(default_factory=dict)
    # D-D: set on steps produced by macro expansion (compile pass 0) — the
    # planner-facing macro verb this atomic step came from, for trace nesting.
    macro_parent: str | None = None


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    """A body's report on a dispatched `SubTask` (mirrors `/l2/task_status`).

    `error_code` and `recovery_actions` are typed (B3). `touched_node_ids` echoes
    the subtask's node ids verbatim (B9). `message` is human-readable only — never
    machine-parsed.
    """

    task_id: str
    subtask_id: str
    status: TaskStatus
    progress: float = 0.0
    error_code: ErrorCode | None = None
    recovery_actions: tuple[RecoveryHint, ...] = ()
    touched_node_ids: tuple[int, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class VerbSpec:
    """One verb-tier entry: a verb the body supports + its parameter keys and
    (for appliance verbs) the appliance types it can drive.
    """

    name: str
    params: tuple[str, ...] = ()
    appliance_types: tuple[str, ...] = ()
    # D-P: optional advisory skill reliability per condition bucket
    # ({"fragile": 0.6}) — shapes planning preferences only; safety gates
    # never read it. Filled by the skillforge scorecard, empty by default.
    reliability: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BodyProfile:
    """The manifest's Body Profile tier (D3, from B2R `embodiment_adaptation.md`).

    Executor-facing hardware identity. The brain does **not** read `joints` /
    `sensors` / `gripper` (those stay below L2); they are carried for the device
    package and introspection. `base_type` is one of ``"wheeled"`` / ``"legged"``
    / ``"fixed"``.
    """

    profile_id: str
    display_name: str
    dof: int
    base_type: str
    joints: dict[str, Any] = field(default_factory=dict)
    sensors: dict[str, Any] = field(default_factory=dict)
    gripper: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    """What a body can do — the two-tier contract the brain queries at plan time.

    The **verb tier** (`verbs`) is what the planner reads to decide what it may
    emit; the **Body Profile tier** (`body_profile`) is executor-facing. A verb
    the body does not declare is refused, never dispatched (D3).
    """

    body_profile: BodyProfile
    verbs: tuple[VerbSpec, ...] = ()

    def verb_names(self) -> frozenset[str]:
        """The set of supported verb names."""
        return frozenset(v.name for v in self.verbs)

    def supports(self, verb: str) -> bool:
        """True if the body declares `verb` in its verb tier."""
        return any(v.name == verb for v in self.verbs)


@runtime_checkable
class ExecutorAdapter(Protocol):
    """The execution seam (D1): the brain dispatches here, a body fills it.

    Lives in the brain because the brain is the caller (same pattern as
    `Reasoner`). `bodylink.MockBody` is the reference fill; real robots ship their
    own. `dispatch` returns a **stream** of `StatusUpdate`s (running → terminal),
    matching the body team's `/l2/task_status` topic — drain it to the terminal
    status. Expected task failure comes back as a `FAILED` `StatusUpdate`, never
    an exception (returns-over-raises); raise only for transport/IO failure.
    """

    def capabilities(self) -> CapabilityManifest: ...

    def dispatch(self, subtask: SubTask) -> Iterator[StatusUpdate]: ...
