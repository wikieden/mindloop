from __future__ import annotations

from mindloop import Answer, ScriptedReasoner, VerbalizerReasoner
from mindloop.reason import _extract_ids


def test_extract_ids_dedup_order() -> None:
    assert _extract_ids("see #3 and #5 and #3 again") == [3, 5]


def test_extract_ids_empty() -> None:
    assert _extract_ids("no ids here") == []


def test_scripted_reasoner_maps_question_and_cites() -> None:
    r = ScriptedReasoner({"q?": "on the table [#7]"})
    a = r.reason("q?", "ctx")
    assert isinstance(a, Answer)
    assert a.text == "on the table [#7]"
    assert a.cited_node_ids == [7]


def test_scripted_reasoner_default() -> None:
    r = ScriptedReasoner(default="dunno")
    assert r.reason("unmatched", "ctx").text == "dunno"


def test_scripted_reasoner_answer_passthrough() -> None:
    fixed = Answer(text="x", cited_node_ids=[1, 2])
    r = ScriptedReasoner({"q": fixed})
    assert r.reason("q", "ctx") is fixed


def test_verbalizer_reasoner_uses_verbalizer_and_cites() -> None:
    class StubVB:
        def __init__(self) -> None:
            self.seen = ""

        def complete(self, prompt: str) -> str:
            self.seen = prompt
            return "the mug is on the table [#2]"

    vb = StubVB()
    a = VerbalizerReasoner(vb).reason("where is the mug?", "SCENE: mug#2")
    assert a.text == "the mug is on the table [#2]"
    assert a.cited_node_ids == [2]
    # both the scene context and the question reached the LLM
    assert "SCENE: mug#2" in vb.seen
    assert "where is the mug?" in vb.seen
