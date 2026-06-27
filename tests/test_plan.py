"""P1 — intent routing + planning skeleton (network-free, ScriptedPlanner + MockBody)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, SpatialMemory

from mindloop import (
    Answer,
    Brain,
    Command,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    TaskStatus,
    compile_commands,
    parse_commands,
)
from mindloop.errors import BrainError

DIM = 16


def _feat(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(DIM).astype("float32")
    return v / np.linalg.norm(v)


@pytest.fixture
def mem(tmp_path) -> SpatialMemory:
    m = SpatialMemory.open(tmp_path / "s.smem", embedding_dim=DIM)
    m.add_detections(
        [
            Detection("bottle", _feat(1), (1.0, 0.3, 0.9), (0.95, 0.25, 0.85), (1.05, 0.35, 0.95)),
            Detection("table", _feat(2), (1.0, 0.3, 0.4), (0.5, -0.2, 0.0), (1.5, 0.8, 0.75)),
        ]
    )
    m.commit()
    return m


def test_task_plans_then_dispatches_with_node_ids(mem: SpatialMemory) -> None:
    router = ScriptedIntentRouter({"bring the bottle": "task"})
    planner = ScriptedPlanner(
        {
            "bring the bottle": (
                Command("navigate", ("bottle",)),
                Command("grasp", ("bottle",)),
                Command("speak", ("here you go",)),
            )
        }
    )
    brain = Brain(mem, ScriptedReasoner(), router=router, planner=planner, executor=MockBody())
    r = brain.handle("bring the bottle")

    assert r.intent == "task"
    assert r.answer is None
    assert [s.verb for s in r.plan.subtasks] == ["navigate", "grasp"]
    # every object slot is bound to a scene-graph node id (B9)
    assert all(s.target_node_ids for s in r.plan.subtasks)
    # speak is carried out-of-band, not dispatched
    assert r.plan.speak == "here you go"
    # B2R-MVP metadata filled by the compiler
    grasp = next(s for s in r.plan.subtasks if s.verb == "grasp")
    assert grasp.skill == "grasp_object"
    assert "robot.hand=empty" in grasp.preconditions
    # dispatched: terminal SUCCESS, node ids echoed back (B9)
    assert len(r.statuses) == 2
    for st, sub in zip(r.statuses, r.plan.subtasks, strict=True):
        assert st.status == TaskStatus.SUCCESS
        assert st.touched_node_ids == sub.target_node_ids


def test_unsupported_verb_is_dropped_not_dispatched(mem: SpatialMemory) -> None:
    # 'fly' is not in the G1-D manifest -> dropped (D3), never reaches the body
    planner = ScriptedPlanner(
        {"go": (Command("fly", ("bottle",)), Command("grasp", ("bottle",)))}
    )
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=planner,
        executor=MockBody(),
    )
    r = brain.handle("go")
    assert [s.verb for s in r.plan.subtasks] == ["grasp"]
    assert len(r.statuses) == 1


def test_question_intent_routes_to_ask(mem: SpatialMemory) -> None:
    brain = Brain(
        mem,
        ScriptedReasoner({"what is here?": "a bottle [#1]"}),
        router=ScriptedIntentRouter({"what is here?": "question"}),
        planner=ScriptedPlanner(),
        executor=MockBody(),
    )
    r = brain.handle("what is here?")
    assert r.intent == "question"
    assert isinstance(r.answer, Answer)
    assert r.plan is None
    assert r.statuses == ()


def test_compile_binds_node_ids_and_fills_metadata(mem: SpatialMemory) -> None:
    plan = compile_commands((Command("grasp", ("bottle",)),), mem, MockBody().capabilities())
    assert len(plan.subtasks) == 1
    st = plan.subtasks[0]
    assert st.verb == "grasp"
    assert st.target_node_ids  # bound to the bottle node
    assert st.skill == "grasp_object"
    assert st.params == {"grasp_type": "side"}


def test_compile_unknown_object_emits_empty_targets(mem: SpatialMemory) -> None:
    # 'spaceship' matches no node -> emitted with empty targets, not dropped
    plan = compile_commands((Command("navigate", ("spaceship",)),), mem, MockBody().capabilities())
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].target_node_ids == ()


def test_parse_commands_text_format() -> None:
    cmds = parse_commands("navigate counter\n- grasp mug\n2. speak here you go\n\n")
    assert cmds[0] == Command("navigate", ("counter",))
    assert cmds[1] == Command("grasp", ("mug",))
    assert cmds[2].verb == "speak"
    assert cmds[2].args == ("here you go",)


def test_speak_fallback_when_planner_omits_it(mem: SpatialMemory) -> None:
    # a planner (weak instruction follower) emits no speak line -> Brain's
    # default_speak floor fills it so a dispatched task still acknowledges
    planner = ScriptedPlanner({"go": (Command("grasp", ("bottle",)),)})
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=planner,
        executor=MockBody(),
        default_speak="好的。",
    )
    r = brain.handle("go")
    assert r.plan.speak == "好的。"
    # but an explicit speak line is preserved, not overridden
    plan = compile_commands(
        (Command("grasp", ("bottle",)), Command("speak", ("here",))),
        mem,
        MockBody().capabilities(),
        default_speak="好的。",
    )
    assert plan.speak == "here"


def test_handle_without_collaborators_raises(mem: SpatialMemory) -> None:
    brain = Brain(mem, ScriptedReasoner())
    with pytest.raises(BrainError):
        brain.handle("do something")


def test_handle_task_without_executor_raises(mem: SpatialMemory) -> None:
    brain = Brain(
        mem,
        ScriptedReasoner(),
        router=ScriptedIntentRouter(default="task"),
        planner=ScriptedPlanner({"go": (Command("grasp", ("bottle",)),)}),
    )
    with pytest.raises(BrainError):
        brain.handle("go")
