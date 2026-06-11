"""Eval-suite v0: cited_node_ids format + validity compliance."""

from __future__ import annotations

from mindloop import ScriptedReasoner, citation_compliance


def test_citation_compliance_rates() -> None:
    ctx = 'SCENE\nobject#3 "mug"\nobject#7 "kettle"'
    cases = [
        ("where is the mug?", ctx),  # cites #3 — valid
        ("where is the kettle?", ctx),  # cites #99 — not in context
        ("what is here?", ctx),  # cites nothing — not format-compliant
    ]
    reasoner = ScriptedReasoner(
        {
            "where is the mug?": "the mug [#3]",
            "where is the kettle?": "the kettle [#99]",
            "what is here?": "some things",
        }
    )
    rep = citation_compliance(reasoner, cases)
    assert rep.total == 3
    assert rep.format_compliant == 2  # mug + kettle cited an id
    assert rep.valid == 1  # only #3 occurs in the context
    assert rep.format_rate == 2 / 3
    assert abs(rep.validity_rate - 1 / 3) < 1e-9
