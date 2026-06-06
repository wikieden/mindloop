"""spatialmem-brain — the brain/LLM layer for SpatialMem.

Binds `spatialmem` (memory) + a Reasoner (LLM) + optional `spatialmem-perception`
(eyes) into one cognitive loop. Holds the concrete LLM integration
(`CosmosReasonVerbalizer`) and the orchestration (`Brain`, `Reasoner`); the core
ships only the `Verbalizer` protocol + `answer()` seam.
"""

from __future__ import annotations

from .brain import Brain
from .reason import Answer, Reasoner, ScriptedReasoner, ToolCall, VerbalizerReasoner
from .verbalizers import CosmosReasonVerbalizer, strip_reasoning

__version__ = "0.1.0a0"

__all__ = [
    "Answer",
    "Brain",
    "CosmosReasonVerbalizer",
    "Reasoner",
    "ScriptedReasoner",
    "ToolCall",
    "VerbalizerReasoner",
    "strip_reasoning",
]
