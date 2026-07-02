"""P5 — dialogue + full S2 loop, incl. the M-L3.3 end-to-end scenario (network-free)."""

from __future__ import annotations

import numpy as np
import pytest
from bodylink import MockBody
from tempomem import Detection, TempoMem

from mindloop import (
    Answer,
    Brain,
    Command,
    Conversation,
    DictPreferenceStore,
    ErrorCode,
    Phylax,
    Policy,
    RecoveryHint,
    RecoveryKind,
    Replanner,
    SafetyContext,
    ScriptedIntentRouter,
    ScriptedPlanner,
    ScriptedReasoner,
    SkillCard,
    SkillCardPlanner,
    SkillLibrary,
    StatusUpdate,
    SubTask,
    TaskStatus,
    TraceStore,
)

DIM = 16


class _CtxReasoner:
    """Records the context it was handed, so dialogue threading can be asserted."""

    def __init__(self) -> None:
        self.last_context = ""

    def reason(self, question: str, context: str) -> Answer:
        self.last_context = context
        return Answer(text=f"re: {question} [#1]", cited_node_ids=[1])


class _FlakyBody(MockBody):
    """Fails the first dispatch of a verb (with a recovery hint), then succeeds."""

    def __init__(self, fail_once: dict[str, ErrorCode]) -> None:
        super().__init__()
        self._fail_once = dict(fail_once)
        self._seen: dict[str, int] = {}

    def _execute(self, subtask: SubTask) -> StatusUpdate:
        v = subtask.verb
        if v in self._fail_once and self._seen.get(v, 0) == 0:
            self._seen[v] = 1
            return StatusUpdate(
                "", subtask.id, TaskStatus.FAILED,
                error_code=self._fail_once[v],
                recovery_actions=(RecoveryHint(RecoveryKind.POSITION_OFFSET, 0.02),),
                touched_node_ids=subtask.target_node_ids,
            )
        return super()._execute(subtask)


@pytest.fixture
def mem(tmp_path) -> TempoMem:
    m = TempoMem.open(tmp_path / "s.smem", embedding_dim=DIM)

    def f(s: int) -> np.ndarray:
        v = np.random.default_rng(s).standard_normal(DIM).astype("float32")
        return v / np.linalg.norm(v)

    m.add_detections(
        [
            Detection("bottle", f(1), (1, 0, 0.9), (0.9, -0.1, 0.8), (1.1, 0.1, 1.0)),
            Detection("door", f(2), (2, 0, 1.0), (1.9, -0.1, 0.0), (2.1, 0.1, 2.0)),
        ]
    )
    m.commit()
    return m


# --------------------------------------------------------------------------- #
# Conversation + dialogue threading
# --------------------------------------------------------------------------- #
def test_history_text_renders_turns(mem: TempoMem) -> None:
    conv = Conversation()
    brain = Brain(mem, ScriptedReasoner({"hi": "hello [#1]"}),
                  router=ScriptedIntentRouter(default="question"), planner=ScriptedPlanner())
    brain.converse("hi", conv)
    assert len(conv) == 1
    assert "User: hi" in conv.history_text()
    assert "Assistant: hello [#1]" in conv.history_text()


def test_converse_threads_dialogue_history(mem: TempoMem) -> None:
    rsn = _CtxReasoner()
    brain = Brain(mem, rsn, router=ScriptedIntentRouter(default="question"),
                  planner=ScriptedPlanner())
    conv = Conversation()
    brain.converse("what is on the table?", conv)
    assert "CONVERSATION" not in rsn.last_context  # first turn: no history
    brain.converse("what about the other one?", conv)
    # the prior turn is now threaded into the reasoner context (dialogue-grounded)
    assert "CONVERSATION" in rsn.last_context
    assert "what is on the table?" in rsn.last_context
    assert len(conv) == 2


# --------------------------------------------------------------------------- #
# L5 preference overlay
# --------------------------------------------------------------------------- #
def _laundry_planner(manifest) -> SkillCardPlanner:
    card = SkillCard.from_dict(
        {
            "id": "laundry_basic",
            "category": "laundry",
            "steps": [
                {"verb": "operate_appliance", "target": "washer",
                 "params": {"program": "normal"}},
            ],
        }
    )
    return SkillCardPlanner(SkillLibrary([card]), manifest)


def test_preference_overrides_card_default(mem: TempoMem) -> None:
    body = MockBody()
    prefs = DictPreferenceStore({"alice": {"program": "eco", "bogus": "x"}})
    brain = Brain(mem, ScriptedReasoner(), router=ScriptedIntentRouter(default="task"),
                  planner=_laundry_planner(body.capabilities()), executor=body, preferences=prefs)
    # alice prefers eco -> overrides the card's program=normal (manifest-gated:
    # 'program' is a declared operate_appliance param; 'bogus' is dropped)
    r = brain.handle("do the laundry", person="alice")
    op = next(s for s in r.plan.subtasks if s.verb == "operate_appliance")
    assert op.params["program"] == "eco"
    assert "bogus" not in op.params
    # bob has no prefs -> the card default stands
    r2 = brain.handle("do the laundry", person="bob")
    op2 = next(s for s in r2.plan.subtasks if s.verb == "operate_appliance")
    assert op2.params["program"] == "normal"


# --------------------------------------------------------------------------- #
# M-L3.3 end-to-end scenario: one conversation through the whole loop
# --------------------------------------------------------------------------- #
def test_full_loop_scenario(mem: TempoMem) -> None:
    body = _FlakyBody({"grasp": ErrorCode.GRASP_FAILED})
    trace = TraceStore(":memory:")
    brain = Brain(
        mem,
        ScriptedReasoner({"what is here?": "a bottle and a door [#1] [#2]"}),
        router=ScriptedIntentRouter({"what is here?": "question"}, default="task"),
        planner=ScriptedPlanner(
            {
                "bring the bottle": (Command("grasp", ("bottle",)),),
                "open the door": (Command("open_door", ("door",)),),
                "grab it": (Command("grasp", ("bottle",)),),
            }
        ),
        executor=body,
        policy=Phylax(Policy(adult_only_verbs=frozenset({"grasp"}))),
        replanner=Replanner(),
        trace=trace,
    )
    conv = Conversation()
    adult, child = SafetyContext(role="adult"), SafetyContext(role="child")

    # 1. question — cited from the scene graph
    r1 = brain.converse("what is here?", conv, safety_context=adult)
    assert r1.intent == "question"
    assert r1.answer is not None and r1.answer.cited_node_ids == [1, 2]

    # 2. task that fails once then recovers via bounded replan (P4)
    r2 = brain.converse("bring the bottle", conv, safety_context=adult)
    assert r2.statuses[-1].status == TaskStatus.SUCCESS
    assert not r2.blocked

    # 3. another task — succeeds outright
    r3 = brain.converse("open the door", conv, safety_context=adult)
    assert r3.statuses[-1].status == TaskStatus.SUCCESS

    # 4. a child tries the adult-only verb -> Phylax blocks it (P3), nothing dispatched
    r4 = brain.converse("grab it", conv, safety_context=child)
    assert r4.blocked
    assert r4.violations[0].rule == "permission.adult_only"
    assert r4.statuses == ()

    # the whole conversation is recorded, and every dispatch is in the trace (B9)
    assert len(conv) == 4
    grasp_records = [r for r in trace.episodes() if r.verb == "grasp"]
    assert any(r.status == "failed" for r in grasp_records)  # the recovered failure
    assert any(r.status == "success" for r in grasp_records)
    assert trace.by_node(1)  # bottle node id touched, queryable
    trace.close()
