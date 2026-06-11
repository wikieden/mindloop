"""Citation-compliance eval: does a Reasoner cite valid node ids, in format?

Two automated, network-free metrics for the eval suite (use with
``ScriptedReasoner`` in tests):

- **format rate** — fraction of answers that cite at least one ``#id``;
- **validity rate** — fraction of answers whose every cited id actually occurs
  in the context handed to the reasoner (a cheap proxy for "the id is real").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .reason import Reasoner

_ID_RE = re.compile(r"#(\d+)")


@dataclass
class CitationReport:
    total: int
    format_compliant: int  # answers citing >= 1 node id
    valid: int  # answers whose cited ids all appear in the context

    @property
    def format_rate(self) -> float:
        return self.format_compliant / self.total if self.total else 0.0

    @property
    def validity_rate(self) -> float:
        return self.valid / self.total if self.total else 0.0


def citation_compliance(reasoner: Reasoner, cases: list[tuple[str, str]]) -> CitationReport:
    """Run ``reasoner`` over ``(question, context)`` cases and score citations.

    An answer is *format-compliant* if it cites >= 1 ``#id`` and *valid* if every
    cited id occurs in that case's context. Deterministic with a scripted
    reasoner; no network.
    """
    fmt = 0
    valid = 0
    for question, context in cases:
        ans = reasoner.reason(question, context)
        ctx_ids = {int(m) for m in _ID_RE.findall(context)}
        if ans.cited_node_ids:
            fmt += 1
            if all(cid in ctx_ids for cid in ans.cited_node_ids):
                valid += 1
    return CitationReport(total=len(cases), format_compliant=fmt, valid=valid)
