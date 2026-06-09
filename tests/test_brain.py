from __future__ import annotations

from tests.conftest import make_det

from spatialmem_brain import Answer, Brain, ScriptedReasoner


def test_brain_ingest_then_ask(mem) -> None:
    brain = Brain(mem, ScriptedReasoner(default="I see things [#1]"))
    brain.ingest([make_det("mug", (1.0, 0.0, 0.9), 1), make_det("table", (1.0, 0.0, 0.4), 2)])
    ans = brain.ask("what's here?")
    assert isinstance(ans, Answer)
    assert ans.text == "I see things [#1]"
    assert ans.cited_node_ids == [1]


def test_brain_ask_passes_serialized_scene_to_reasoner(mem) -> None:
    seen: dict[str, str] = {}

    class EchoReasoner:
        def reason(self, question: str, context: str) -> Answer:
            seen["ctx"] = context
            seen["q"] = question
            return Answer(text="ok")

    brain = Brain(mem, EchoReasoner())
    brain.ingest([make_det("mug", (1.0, 0.0, 0.9), 1)])
    brain.ask("where?")
    assert "mug" in seen["ctx"]  # the serialized scene reached the reasoner
    assert seen["q"] == "where?"


def test_brain_ask_serializes_query_subgraph_not_whole_scene(mem) -> None:
    """A relevant-but-old node survives a tight budget because ask() serializes
    the query subgraph, not the whole scene (which would drop it by recency)."""
    seen: dict[str, str] = {}

    class EchoReasoner:
        def reason(self, question: str, context: str) -> Answer:
            seen["ctx"] = context
            return Answer(text="ok")

    brain = Brain(mem, EchoReasoner(), max_tokens=40)
    brain.ingest(
        [make_det(f"obj{i}", (float(i) * 2, 0.0, 0.0), i + 1, ts=float(i)) for i in range(20)]
    )
    brain.ask("obj0")  # obj0 is the oldest — dropped by a 40-token whole-scene budget
    assert '"obj0"' in seen["ctx"]  # query surfaced it despite the tight budget


def test_brain_ask_falls_back_to_whole_scene_when_query_empty(mem) -> None:
    seen: dict[str, str] = {}

    class EchoReasoner:
        def reason(self, question: str, context: str) -> Answer:
            seen["ctx"] = context
            return Answer(text="ok")

    brain = Brain(mem, EchoReasoner())
    brain.ingest([make_det("mug", (1.0, 0.0, 0.9), 1)])
    brain.ask("zzzz-no-such-object-xyz")
    assert "mug" in seen["ctx"]  # nothing matched -> whole scene served
