"""D-I — fungibility-aware object-binding ambiguity.

The compiler queries k=3 and flags a binding as ambiguous ONLY when the close
candidates are semantically non-interchangeable: different labels near-equal in
score, or a qualified mention ("red cup") that multiple same-label candidates
still satisfy. Generic mention over identical items (5 napkins) is fungible —
auto-bind top-1, never ask. An ambiguous plan asks the Clarifier once (shared
per-task ask budget) before Phylax/dispatch; with no clarifier it proceeds on
top-1 (logged), exactly as before.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Brain,
    Command,
    ErrorCode,
    Replanner,
    ScriptedClarifier,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
)
from mindloop.plan import compile_commands

_MANIFEST = MockBody().capabilities()


class _StubMem:
    """mention -> [(id, label, score)] — only the query seam the compiler uses."""

    def __init__(self, hits: dict[str, list[tuple[int, str, float]]]) -> None:
        self._hits = hits

    def query(self, mention: str, k: int = 1):
        ns = [
            SimpleNamespace(id=i, label=lb, score=s) for i, lb, s in self._hits.get(mention, [])
        ][:k]
        return SimpleNamespace(nodes=ns)


def _compile(mem, *cmds: Command):
    return compile_commands(tuple(cmds), mem, _MANIFEST)


# --------------------------------------------------------------------------- #
# compiler-level rules
# --------------------------------------------------------------------------- #
def test_different_labels_close_in_score_is_ambiguous() -> None:
    mem = _StubMem({"cup": [(3, "mug", 0.90), (5, "cup", 0.88)]})
    plan = _compile(mem, Command("grasp", ("cup",)))
    assert plan.ambiguities and plan.ambiguities[0].mention == "cup"
    assert {nid for nid, _ in plan.ambiguities[0].candidates} == {3, 5}
    # still bound top-1 so a clarifier-less brain can proceed
    assert plan.subtasks[0].target_node_ids == (3,)


def test_fungible_same_label_no_qualifier_binds_silently() -> None:
    mem = _StubMem({"napkin": [(1, "napkin", 0.9), (2, "napkin", 0.9), (3, "napkin", 0.9)]})
    plan = _compile(mem, Command("grasp", ("napkin",)))
    assert plan.ambiguities == ()
    assert plan.subtasks[0].target_node_ids == (1,)


def test_qualified_mention_over_same_label_candidates_is_ambiguous() -> None:
    mem = _StubMem({"red cup": [(1, "cup", 0.9), (2, "cup", 0.88)]})
    plan = _compile(mem, Command("grasp", ("red cup",)))
    assert plan.ambiguities and plan.ambiguities[0].mention == "red cup"


def test_single_candidate_is_never_ambiguous() -> None:
    mem = _StubMem({"cup": [(1, "cup", 0.9)]})
    plan = _compile(mem, Command("grasp", ("cup",)))
    assert plan.ambiguities == ()


def test_distant_second_candidate_is_not_ambiguous() -> None:
    # the second label is different but nowhere near in score -> top-1 wins
    mem = _StubMem({"cup": [(1, "cup", 0.9), (2, "mug", 0.2)]})
    plan = _compile(mem, Command("grasp", ("cup",)))
    assert plan.ambiguities == ()


# --------------------------------------------------------------------------- #
# brain-level: ask once, fold the answer, share the ask budget
# --------------------------------------------------------------------------- #
def _mem_two_cups() -> TempoMem:
    mem = TempoMem.open(":memory:", embedding_dim=4)
    v = np.ones(4, dtype="float32") / 2.0
    # far apart so fusion keeps two distinct "cup" nodes
    for cx in (0.5, 4.5):
        mem.add_detections(
            [Detection("cup", v, (cx, 0.0, 0.5), (cx - 0.1, -0.1, 0.4), (cx + 0.1, 0.1, 0.6))]
        )
        mem.commit()
    return mem


def _brain(mem, *, plans, clarifier=None, fail=None, ask_budget=2) -> Brain:
    return Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter({}, default="task"),
        planner=ScriptedPlanner(plans),
        executor=MockBody(fail=fail or {}),
        replanner=Replanner(),
        clarifier=clarifier,
        ask_budget=ask_budget,
    )


def test_ambiguous_binding_asks_then_resolves() -> None:
    mem = _mem_two_cups()
    plans = {
        "grab the red cup": (Command("grasp", ("red cup",)),),
        # the folded answer re-plans to an unqualified (fungible) mention
        "grab the red cup (the left one)": (Command("grasp", ("cup",)),),
    }
    clarifier = ScriptedClarifier(default="the left one")
    r = _brain(mem, plans=plans, clarifier=clarifier).handle("grab the red cup")
    assert len(clarifier.asked) == 1
    assert "red cup" in clarifier.asked[0]
    assert r.statuses and r.statuses[-1].status.value == "success"


def test_no_clarifier_proceeds_on_top1() -> None:
    mem = _mem_two_cups()
    plans = {"grab the red cup": (Command("grasp", ("red cup",)),)}
    r = _brain(mem, plans=plans).handle("grab the red cup")
    assert r.statuses and r.statuses[-1].status.value == "success"


def test_binding_ask_counts_against_task_budget() -> None:
    mem = _mem_two_cups()
    plans = {
        "grab the red cup": (Command("grasp", ("red cup",)),),
        "grab the red cup (the left one)": (Command("grasp", ("cup",)),),
    }
    clarifier = ScriptedClarifier(default="the left one")
    # budget 1: the binding ask consumes it; the persistent grasp failure's
    # dead-end ESCALATE must then stop honestly WITHOUT a second ask
    r = _brain(
        mem,
        plans=plans,
        clarifier=clarifier,
        fail={"grasp": ErrorCode.BATTERY_LOW},
        ask_budget=1,
    ).handle("grab the red cup")
    assert len(clarifier.asked) == 1
    assert r.plan is not None and r.plan.speak  # honest escalation speak


def test_zero_score_ties_are_ambiguous_when_labels_differ() -> None:
    # MEDIUM-2: keyword backends can return score 0.0 for every candidate — a
    # zero-score tie is maximal uncertainty, not silence
    mem = _StubMem({"cup": [(1, "cup", 0.0), (2, "mug", 0.0)]})
    plan = _compile(mem, Command("grasp", ("cup",)))
    assert plan.ambiguities and {n for n, _ in plan.ambiguities[0].candidates} == {1, 2}
