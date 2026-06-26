"""mindloop — the brain/LLM layer for Chronotope.

Binds `tempomem` (memory) + a Reasoner (LLM) + optional `worldsense`
(eyes) into one cognitive loop. Holds the concrete LLM integration
(`CosmosReasonVerbalizer`) and the orchestration (`Brain`, `Reasoner`); the core
ships only the `Verbalizer` protocol + `answer()` seam.
"""

from __future__ import annotations

from .brain import Brain
from .errors import BrainError
from .eval import CitationReport, citation_compliance
from .execute import (
    BodyProfile,
    CapabilityManifest,
    ErrorCode,
    ExecutorAdapter,
    RecoveryHint,
    RecoveryKind,
    StatusUpdate,
    SubTask,
    TaskStatus,
    VerbSpec,
)
from .health import HealthReport
from .plan import (
    Command,
    HandleResult,
    IntentRouter,
    Plan,
    Planner,
    ScriptedIntentRouter,
    ScriptedPlanner,
    VerbalizerIntentRouter,
    VerbalizerPlanner,
    compile_commands,
    parse_commands,
)
from .preference import PreferenceStore
from .reason import Answer, Reasoner, ScriptedReasoner, ToolCall, VerbalizerReasoner
from .verbalizers import CosmosReasonVerbalizer, strip_reasoning

__version__ = "0.1.0a0"

__all__ = [
    "Answer",
    "BodyProfile",
    "Brain",
    "BrainError",
    "CapabilityManifest",
    "CitationReport",
    "Command",
    "CosmosReasonVerbalizer",
    "ErrorCode",
    "ExecutorAdapter",
    "HandleResult",
    "HealthReport",
    "IntentRouter",
    "Plan",
    "Planner",
    "PreferenceStore",
    "Reasoner",
    "RecoveryHint",
    "RecoveryKind",
    "ScriptedIntentRouter",
    "ScriptedPlanner",
    "ScriptedReasoner",
    "StatusUpdate",
    "SubTask",
    "TaskStatus",
    "ToolCall",
    "VerbSpec",
    "VerbalizerIntentRouter",
    "VerbalizerPlanner",
    "VerbalizerReasoner",
    "citation_compliance",
    "compile_commands",
    "parse_commands",
    "strip_reasoning",
]
