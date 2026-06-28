"""P2 — Episteme skill-card library (network-free; dict cards + MockBody)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, SpatialMemory

from mindloop import (
    Brain,
    Command,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    SkillCard,
    SkillCardPlanner,
    SkillLibrary,
    TaskStatus,
    compile_commands,
    extract_slots,
    instantiate,
)


def _laundry() -> SkillCard:
    return SkillCard.from_dict(
        {
            "id": "laundry_basic",
            "category": "laundry",
            "steps": [
                {"verb": "navigate", "target": "washer"},
                {"verb": "open_door", "target": "washer"},
                {"verb": "grasp", "target": "clothes"},
                {"verb": "place", "target": "washer"},
                {
                    "verb": "operate_appliance",
                    "target": "washer",
                    "params": {"program": "normal", "temperature_c": 40},
                },
                {"verb": "speak", "target": "Starting the wash now."},
            ],
            "rules": [
                {
                    "when": {"fabric": "wool"},
                    "target_verb": "operate_appliance",
                    "set_params": {"program": "delicate", "temperature_c": 30},
                },
                {
                    "when": {"color": "dark"},
                    "target_verb": "operate_appliance",
                    "set_params": {"temperature_c": 30},
                },
            ],
        }
    )


@pytest.fixture
def manifest():
    return MockBody().capabilities()


# --------------------------------------------------------------------------- #
# instantiation + rules
# --------------------------------------------------------------------------- #
def test_instantiate_default_program(manifest) -> None:
    cmds = instantiate(_laundry(), manifest)
    assert [c.verb for c in cmds] == [
        "navigate",
        "open_door",
        "grasp",
        "place",
        "operate_appliance",
        "speak",
    ]
    op = next(c for c in cmds if c.verb == "operate_appliance")
    assert op.params == {"program": "normal", "temperature_c": 40}
    # speak keeps its full message as the single arg
    assert cmds[-1].args == ("Starting the wash now.",)


def test_wool_rule_overlays_delicate(manifest) -> None:
    slots = {"fabric": "wool"}
    cmds = instantiate(_laundry(), manifest, slots=slots)
    op = next(c for c in cmds if c.verb == "operate_appliance")
    assert op.params == {"program": "delicate", "temperature_c": 30}


def test_dark_color_rule_lowers_temp_only(manifest) -> None:
    cmds = instantiate(_laundry(), manifest, slots={"color": "dark"})
    op = next(c for c in cmds if c.verb == "operate_appliance")
    assert op.params == {"program": "normal", "temperature_c": 30}


def test_unsupported_card_verb_dropped(manifest) -> None:
    card = SkillCard.from_dict(
        {
            "id": "x",
            "category": "x",
            "steps": [{"verb": "fly"}, {"verb": "navigate", "target": "x"}],
        }
    )
    cmds = instantiate(card, manifest)
    assert [c.verb for c in cmds] == ["navigate"]


def test_preferences_only_set_known_params(manifest) -> None:
    # preference 'program' is a declared operate_appliance param -> applied;
    # 'bogus' is not a declared param for any verb -> ignored
    card = _laundry()
    cmds = instantiate(card, manifest, preferences={"program": "eco", "bogus": "x"})
    op = next(c for c in cmds if c.verb == "operate_appliance")
    assert op.params["program"] == "eco"
    assert "bogus" not in op.params


# --------------------------------------------------------------------------- #
# slot extraction
# --------------------------------------------------------------------------- #
def test_extract_slots_from_instruction() -> None:
    card = _laundry()
    assert extract_slots("please wash the wool sweater", card) == {"fabric": "wool"}
    assert extract_slots("wash my dark jeans", card) == {"color": "dark"}
    assert extract_slots("wash the shirt", card) == {}


# --------------------------------------------------------------------------- #
# library retrieval (keyword + semantic BYO encoder)
# --------------------------------------------------------------------------- #
class _HashEncoder:
    """Deterministic, network-free text encoder for retrieval tests."""

    def __init__(self, dim: int = 32) -> None:
        self.dim = dim

    def encode_text(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype="float32")
        for tok in text.lower().split():
            # deterministic (not builtin hash(), which is salted per process)
            bucket = sum(ord(ch) for ch in tok) % self.dim
            v[bucket] += 1.0
        return v


def _cook() -> SkillCard:
    return SkillCard.from_dict(
        {
            "id": "cook_pasta",
            "category": "pasta",
            "steps": [{"verb": "navigate", "target": "stove"}],
        }
    )


def test_keyword_retrieval_picks_right_card() -> None:
    lib = SkillLibrary([_laundry(), _cook()])
    assert lib.retrieve("do the laundry")[0].id == "laundry_basic"
    assert lib.retrieve("make some pasta")[0].id == "cook_pasta"
    assert lib.retrieve("fix the spaceship") == []  # no keyword overlap


def test_semantic_retrieval_with_encoder() -> None:
    lib = SkillLibrary([_laundry(), _cook()])
    enc = _HashEncoder()
    assert lib.retrieve("laundry", encoder=enc, k=1)[0].id == "laundry_basic"


# --------------------------------------------------------------------------- #
# SkillCardPlanner: library-first, LLM fallback
# --------------------------------------------------------------------------- #
def test_planner_uses_card_when_matched(manifest) -> None:
    lib = SkillLibrary([_laundry()])
    planner = SkillCardPlanner(lib, manifest)
    cmds = planner.plan("wash the wool sweater", context="")
    op = next(c for c in cmds if c.verb == "operate_appliance")
    assert op.params["program"] == "delicate"  # wool slot extracted + rule fired


def test_planner_falls_back_when_no_card(manifest) -> None:
    lib = SkillLibrary([_laundry()])
    fallback = ScriptedPlanner({"open the door": (Command("open_door", ("door",)),)})
    planner = SkillCardPlanner(lib, manifest, fallback=fallback)
    cmds = planner.plan("open the door", context="")
    assert [c.verb for c in cmds] == ["open_door"]


def test_planner_empty_without_fallback(manifest) -> None:
    planner = SkillCardPlanner(SkillLibrary([_laundry()]), manifest)
    assert planner.plan("fix the spaceship", context="") == ()


# --------------------------------------------------------------------------- #
# compile + end-to-end dispatch through Brain
# --------------------------------------------------------------------------- #
def test_compile_carries_card_params(manifest) -> None:
    cmds = instantiate(_laundry(), manifest, slots={"fabric": "wool"})
    mem = SpatialMemory.open(":memory:", embedding_dim=8)
    plan = compile_commands(cmds, mem, manifest)
    op = next(s for s in plan.subtasks if s.verb == "operate_appliance")
    assert op.params["program"] == "delicate"  # card param survived compilation
    assert plan.speak == "Starting the wash now."


def test_brain_handle_runs_card_end_to_end(tmp_path) -> None:
    mem = SpatialMemory.open(tmp_path / "s.smem", embedding_dim=8)
    f = lambda s: (lambda v: v / np.linalg.norm(v))(  # noqa: E731
        np.random.default_rng(s).standard_normal(8).astype("float32")
    )
    mem.add_detections(
        [
            Detection("washer", f(1), (2.0, 0.0, 0.5), (1.8, -0.3, 0.0), (2.2, 0.3, 1.0)),
            Detection("clothes", f(2), (1.0, 0.5, 0.4), (0.9, 0.4, 0.3), (1.1, 0.6, 0.5)),
        ]
    )
    mem.commit()
    manifest = MockBody().capabilities()
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=SkillCardPlanner(SkillLibrary([_laundry()]), manifest),
        executor=MockBody(),
    )
    r = brain.handle("wash the wool sweater")
    assert r.intent == "task"
    assert [s.verb for s in r.plan.subtasks][-1] == "operate_appliance"
    op = next(s for s in r.plan.subtasks if s.verb == "operate_appliance")
    assert op.params["program"] == "delicate"
    assert r.plan.speak == "Starting the wash now."
    assert all(st.status == TaskStatus.SUCCESS for st in r.statuses)
    # the washer object slot bound to a scene-graph node id (B9)
    nav = next(s for s in r.plan.subtasks if s.verb == "navigate")
    assert nav.target_node_ids


# --------------------------------------------------------------------------- #
# YAML loader (needs the 'skills' extra; skip if PyYAML absent)
# --------------------------------------------------------------------------- #
def test_load_cards_from_yaml_dir(manifest) -> None:
    pytest.importorskip("yaml")
    from pathlib import Path

    from mindloop import load_cards

    cards_dir = Path(__file__).resolve().parent.parent / "cards"
    cards = load_cards(cards_dir)
    ids = {c.id for c in cards}
    assert {"laundry_basic", "cook_pasta"} <= ids
    laundry = next(c for c in cards if c.id == "laundry_basic")
    cmds = instantiate(laundry, manifest, slots={"fabric": "wool"})
    op = next(c for c in cmds if c.verb == "operate_appliance")
    assert op.params["program"] == "delicate"
