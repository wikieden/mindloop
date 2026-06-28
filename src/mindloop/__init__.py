"""mindloop — the brain/LLM layer for Chronotope.

Binds `tempomem` (memory) + a Reasoner (LLM) + optional `worldsense`
(eyes) into one cognitive loop. Holds the concrete LLM integration
(`CosmosReasonVerbalizer`) and the orchestration (`Brain`, `Reasoner`); the core
ships only the `Verbalizer` protocol + `answer()` seam.
"""

from __future__ import annotations

from .brain import Brain
from .episteme import (
    Rule,
    SkillCard,
    SkillCardPlanner,
    SkillLibrary,
    SkillStep,
    extract_slots,
    instantiate,
    load_cards,
)
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
from .phylax import (
    Phylax,
    Policy,
    Role,
    SafetyContext,
    Severity,
    Violation,
    refusal_speak,
)
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
from .replan import ReplanAction, ReplanDecision, Replanner
from .trace import TraceRecord, TraceStore
from .verbalizers import CosmosReasonVerbalizer, FailoverVerbalizer, strip_reasoning

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
    "FailoverVerbalizer",
    "HandleResult",
    "HealthReport",
    "IntentRouter",
    "Phylax",
    "Plan",
    "Planner",
    "Policy",
    "PreferenceStore",
    "Reasoner",
    "RecoveryHint",
    "RecoveryKind",
    "ReplanAction",
    "ReplanDecision",
    "Replanner",
    "Role",
    "Rule",
    "SafetyContext",
    "ScriptedIntentRouter",
    "ScriptedPlanner",
    "ScriptedReasoner",
    "Severity",
    "SkillCard",
    "SkillCardPlanner",
    "SkillLibrary",
    "SkillStep",
    "StatusUpdate",
    "SubTask",
    "TaskStatus",
    "ToolCall",
    "TraceRecord",
    "TraceStore",
    "VerbSpec",
    "VerbalizerIntentRouter",
    "VerbalizerPlanner",
    "VerbalizerReasoner",
    "Violation",
    "citation_compliance",
    "compile_commands",
    "extract_slots",
    "instantiate",
    "load_cards",
    "parse_commands",
    "refusal_speak",
    "strip_reasoning",
]
