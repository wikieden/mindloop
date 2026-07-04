"""D-D — macro expansion, the compile pipeline's pass 0.

Planner-facing macros (`deliver`, `sweep`, `mop`) expand to atomic steps BEFORE
node binding and the manifest gate, so Phylax and the manifest check see the
real work, never the macro. Expansion is single-pass (mop's atomic core is not
re-expanded); children carry ``macro_parent`` for trace nesting.
"""

from __future__ import annotations

from bodylink import MockBody

from mindloop import (
    Command,
    Phylax,
    Policy,
    SafetyContext,
    StatusUpdate,
    SubTask,
    TaskStatus,
    TraceStore,
)
from mindloop.plan import compile_commands

_MANIFEST = MockBody().capabilities()


def test_deliver_expands_to_navigate_offer(mem) -> None:
    plan = compile_commands((Command("deliver", ("tea", "table")),), mem, _MANIFEST)
    assert tuple(s.verb for s in plan.subtasks) == ("navigate", "offer")
    nav, offer = plan.subtasks
    assert nav.named_params.get("target") == "table"
    assert offer.named_params == {"item": "tea", "recipient": "table"}
    assert all(s.macro_parent == "deliver" for s in plan.subtasks)


def test_sweep_expands_to_navigate_vacuum(mem) -> None:
    plan = compile_commands((Command("sweep", ("kitchen",)),), mem, _MANIFEST)
    assert tuple(s.verb for s in plan.subtasks) == ("navigate", "vacuum")
    assert all(s.macro_parent == "sweep" for s in plan.subtasks)


def test_mop_expands_with_wet_floor_warnings(mem) -> None:
    plan = compile_commands((Command("mop", ("kitchen",)),), mem, _MANIFEST)
    assert tuple(s.verb for s in plan.subtasks) == (
        "warn_wet_floor",
        "navigate",
        "mop",  # the atomic core — single-pass, never re-expanded
        "warn_wet_floor",
    )
    assert all(s.macro_parent == "mop" for s in plan.subtasks)


def test_atomic_verbs_stay_unexpanded(mem) -> None:
    plan = compile_commands(
        (Command("navigate", ("table",)), Command("grasp", ("mug",))), mem, _MANIFEST
    )
    assert tuple(s.verb for s in plan.subtasks) == ("navigate", "grasp")
    assert all(s.macro_parent is None for s in plan.subtasks)


def test_phylax_checks_the_expanded_steps(mem) -> None:
    # the macro verb never reaches Phylax — its expanded child (vacuum@kitchen)
    # is what trips the D-A service-region gate
    plan = compile_commands((Command("sweep", ("kitchen",)),), mem, _MANIFEST)
    gate = Phylax(Policy(service_permitted_regions={"kitchen": frozenset({"cleaner"})}))
    violations = gate.check(plan, SafetyContext(role="adult", robot_service="host"))
    assert violations and violations[0].rule == "service.region_access"


def test_trace_records_macro_parent() -> None:
    tr = TraceStore(":memory:")
    st = SubTask(id="m0", verb="vacuum", target_node_ids=(4,), macro_parent="sweep")
    tr.log_attempt(
        st,
        StatusUpdate(task_id="t", subtask_id="m0", status=TaskStatus.SUCCESS, message="done"),
        session_id="s1",
    )
    rows = tr.episodes(session_id="s1")
    assert rows and rows[0].macro_parent == "sweep"
    tr.close()


def test_deliver_with_missing_destination_warns_and_degrades(mem, caplog) -> None:
    # MEDIUM-1: deliver structurally needs (item, recipient); with only the item
    # the navigate child has no destination — compile best-effort but warn loudly
    import logging

    with caplog.at_level(logging.WARNING, logger="mindloop.plan"):
        plan = compile_commands((Command("deliver", ("tea",)),), mem, _MANIFEST)
    assert tuple(s.verb for s in plan.subtasks) == ("navigate", "offer")
    assert any("deliver" in r.message and "missing" in r.message for r in caplog.records)
