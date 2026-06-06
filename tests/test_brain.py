from __future__ import annotations

from spatialmem_brain import Answer, Brain, ScriptedReasoner
from tests.conftest import make_det


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
