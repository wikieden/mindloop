"""Step-3 Phylax extensions — D1 param gating · D-A robot_service · Q6 region
defaults · D-K menu/allergen invariant (+ the D-C-minimal `named_params` they
read). TASK-FAMILIES §5d/§7d ratified decisions; TDD-first per DEV-STATUS T2."""

from __future__ import annotations

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    MenuKB,
    Phylax,
    Policy,
    SafetyContext,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    load_menu,
)
from mindloop.plan import compile_commands

_DIM = 8


def _mem(*names: str) -> TempoMem:
    mem = TempoMem.open(":memory:", embedding_dim=_DIM)
    rng = np.random.default_rng(0)
    for i, name in enumerate(names):
        v = rng.standard_normal(_DIM).astype("float32")
        c = (float(i), 0.0, 0.5)
        mem.add_detections(
            [
                Detection(
                    name, v / np.linalg.norm(v), c, (c[0] - 0.1, -0.1, 0.4), (c[0] + 0.1, 0.1, 0.6)
                )
            ]
        )
    mem.commit()
    return mem


def _plan(mem: TempoMem, *cmds: Command):
    return compile_commands(tuple(cmds), mem, MockBody().capabilities())


# --------------------------------------------------------------------------- #
# D-C minimal: named_params from the manifest's declared param names
# --------------------------------------------------------------------------- #
def test_compile_fills_named_params_from_manifest() -> None:
    mem = _mem("water", "cup")
    plan = _plan(mem, Command("pour", ("water", "cup")))
    assert plan.subtasks[0].named_params == {"liquid": "water", "container": "cup"}


def test_compile_named_params_partial_args() -> None:
    mem = _mem("bottle")
    plan = _plan(mem, Command("place", ("bottle",)))  # location omitted
    assert plan.subtasks[0].named_params == {"target": "bottle"}


# --------------------------------------------------------------------------- #
# D1: param-scoped (verb, param) gating — stove adult-only, washer open
# --------------------------------------------------------------------------- #
_D1 = Policy(adult_only_verb_params={"operate_appliance": {"appliance_type": frozenset({"stove"})}})


def _appliance(appliance_type: str) -> Command:
    return Command("operate_appliance", ("kitchen",), {"appliance_type": appliance_type})


def test_child_stove_blocked_washer_open() -> None:
    mem = _mem("kitchen")
    gate = Phylax(_D1)
    stove = _plan(mem, _appliance("stove"))
    washer = _plan(mem, _appliance("washer"))
    child = SafetyContext(role="child")
    assert any(v.rule == "permission.adult_only_param" for v in gate.check(stove, child))
    assert gate.check(washer, child) == ()


def test_adult_stove_clears() -> None:
    mem = _mem("kitchen")
    gate = Phylax(_D1)
    assert gate.check(_plan(mem, _appliance("stove")), SafetyContext(role="adult")) == ()


# --------------------------------------------------------------------------- #
# D-A: robot_service x region gate (requester gate untouched)
# --------------------------------------------------------------------------- #
_DA = Policy(
    service_permitted_regions={
        "private-office": frozenset(),
        "bathroom": frozenset({"cleaner", "guide"}),
    }
)


def test_cleaner_may_enter_bathroom_host_may_not() -> None:
    mem = _mem("bathroom")
    gate = Phylax(_DA)
    plan = _plan(mem, Command("navigate", ("bathroom",)))
    assert gate.check(plan, SafetyContext(role="adult", robot_service="cleaner")) == ()
    got = gate.check(plan, SafetyContext(role="adult", robot_service="host"))
    assert any(v.rule == "service.region_access" for v in got)


def test_no_service_skips_the_gate() -> None:
    mem = _mem("private-office")
    gate = Phylax(_DA)
    plan = _plan(mem, Command("navigate", ("private-office",)))
    assert gate.check(plan, SafetyContext(role="adult")) == ()  # robot_service=None


# --------------------------------------------------------------------------- #
# Q6: default-allow + denylist + unknown-region-refuse (guest/stranger only)
# --------------------------------------------------------------------------- #
_Q6 = Policy(
    known_regions=frozenset({"kitchen", "living room", "bedroom"}),
    guest_blocked_regions=frozenset({"bedroom"}),
)


def test_guest_denylist_blocks_bedroom() -> None:
    mem = _mem("bedroom")
    gate = Phylax(_Q6)
    plan = _plan(mem, Command("navigate", ("bedroom",)))
    got = gate.check(plan, SafetyContext(role="guest"))
    assert any(v.rule == "region.guest_blocked" for v in got)


def test_guest_default_allow_on_known_region() -> None:
    mem = _mem("kitchen")
    gate = Phylax(_Q6)
    assert (
        gate.check(_plan(mem, Command("navigate", ("kitchen",))), SafetyContext(role="guest")) == ()
    )


def test_guest_unknown_region_refused() -> None:
    mem = _mem("attic")
    gate = Phylax(_Q6)
    got = gate.check(_plan(mem, Command("navigate", ("attic",))), SafetyContext(role="guest"))
    assert any(v.rule == "region.unknown" for v in got)


def test_adult_unaffected_by_region_gates() -> None:
    mem = _mem("bedroom")
    gate = Phylax(_Q6)
    assert (
        gate.check(_plan(mem, Command("navigate", ("bedroom",))), SafetyContext(role="adult")) == ()
    )


# --------------------------------------------------------------------------- #
# D-K / D-L: menu KB + allergen invariant (fail-closed)
# --------------------------------------------------------------------------- #
def test_builtin_menu_loads_and_looks_up() -> None:
    kb = load_menu("builtin")
    assert "milk" in kb.allergens("latte", trusted=frozenset({"builtin"}))


def test_unvetted_provenance_reads_unknown() -> None:
    kb = MenuKB({"mystery": (frozenset({"milk"}), "random-url")})
    assert kb.allergens("mystery", trusted=frozenset({"builtin"})) is None


_KB = load_menu("builtin")
_DK = Policy(menu=_KB)


def _serve(item: str) -> Command:
    return Command("offer", (item, "guest_a"))


def test_allergen_intersection_blocks_serve() -> None:
    mem = _mem("latte", "guest_a")
    gate = Phylax(_DK)
    got = gate.check(
        _plan(mem, _serve("latte")),
        SafetyContext(role="adult", allergies=frozenset({"milk"}), allergy_status_known=True),
    )
    assert any(v.rule == "allergy.blocked" for v in got)


def test_no_allergy_serve_clears() -> None:
    mem = _mem("water", "guest_a")
    gate = Phylax(_DK)
    assert (
        gate.check(
            _plan(mem, _serve("water")),
            SafetyContext(role="adult", allergy_status_known=True),
        )
        == ()
    )


def test_unknown_allergy_status_blocks_serving(caplog) -> None:
    # D-L fail-closed: allergy status never asked -> serve-class verbs blocked
    mem = _mem("water", "guest_a")
    gate = Phylax(_DK)
    got = gate.check(_plan(mem, _serve("water")), SafetyContext(role="adult"))
    assert any(v.rule == "allergy.status_unknown" for v in got)


def test_unknown_drink_blocks_for_allergic_guest() -> None:
    mem = _mem("housemade-special", "guest_a")
    gate = Phylax(_DK)
    got = gate.check(
        _plan(mem, _serve("housemade-special")),
        SafetyContext(role="adult", allergies=frozenset({"peanut"}), allergy_status_known=True),
    )
    assert any(v.rule == "allergy.unknown_recipe" for v in got)


def test_no_menu_configured_skips_allergy_gate() -> None:
    mem = _mem("latte", "guest_a")
    gate = Phylax(Policy())
    assert gate.check(_plan(mem, _serve("latte")), SafetyContext(role="adult")) == ()


# --------------------------------------------------------------------------- #
# end-to-end: the gates run inside Brain.converse / handle
# --------------------------------------------------------------------------- #
def test_brain_blocks_child_stove_end_to_end() -> None:
    mem = _mem("kitchen")
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=ScriptedPlanner({"run the stove": (_appliance("stove"),)}),
        executor=MockBody(),
        policy=Phylax(_D1),
    )
    r = brain.handle("run the stove", safety_context=SafetyContext(role="child"))
    assert r.blocked
    assert r.statuses == ()
