"""mindloop — the brain/LLM layer for Chronotope.

Binds `tempomem` (memory) + a Reasoner (LLM) + optional `worldsense`
(eyes) into one cognitive loop. Holds the concrete LLM integration
(`CosmosReasonVerbalizer`) and the orchestration (`Brain`, `Reasoner`); the core
ships only the `Verbalizer` protocol + `answer()` seam.
"""

from __future__ import annotations

from .active_perception import ActivePerception, ScriptedPerception
from .brain import Brain
from .dialogue import Conversation, Turn
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
from .eval import (
    CitationReport,
    EvalCase,
    EvalReport,
    EvalThresholds,
    citation_compliance,
    run_eval,
)
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
from .preference import DictPreferenceStore, PreferenceStore
from .reason import Answer, Reasoner, ScriptedReasoner, ToolCall, VerbalizerReasoner
from .replan import ReplanAction, ReplanDecision, Replanner
from .scene_context import DefaultSceneContextProvider, Focus, SceneContextProvider
from .trace import TraceRecord, TraceStore
from .verbalizers import CosmosReasonVerbalizer, FailoverVerbalizer, strip_reasoning
from .voice import Listener, MockListener, MockSpeaker, Speaker, VoiceLoop, reply_text
from .world_state import Effect, EffectApplier, WorldState, parse_effect

__version__ = "0.1.0a0"

__all__ = [
    "ActivePerception",
    "Answer",
    "BodyProfile",
    "Brain",
    "BrainError",
    "CapabilityManifest",
    "CitationReport",
    "Command",
    "Conversation",
    "CosmosReasonVerbalizer",
    "DefaultSceneContextProvider",
    "DictPreferenceStore",
    "Effect",
    "EffectApplier",
    "ErrorCode",
    "EvalCase",
    "EvalReport",
    "EvalThresholds",
    "ExecutorAdapter",
    "FailoverVerbalizer",
    "Focus",
    "HandleResult",
    "HealthReport",
    "IntentRouter",
    "Listener",
    "MockListener",
    "MockSpeaker",
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
    "SceneContextProvider",
    "ScriptedIntentRouter",
    "ScriptedPerception",
    "ScriptedPlanner",
    "ScriptedReasoner",
    "Severity",
    "SkillCard",
    "SkillCardPlanner",
    "SkillLibrary",
    "SkillStep",
    "Speaker",
    "StatusUpdate",
    "SubTask",
    "TaskStatus",
    "ToolCall",
    "TraceRecord",
    "TraceStore",
    "Turn",
    "VerbSpec",
    "VerbalizerIntentRouter",
    "VerbalizerPlanner",
    "VerbalizerReasoner",
    "Violation",
    "VoiceLoop",
    "WorldState",
    "citation_compliance",
    "compile_commands",
    "extract_slots",
    "instantiate",
    "load_cards",
    "parse_commands",
    "parse_effect",
    "refusal_speak",
    "reply_text",
    "run_eval",
    "strip_reasoning",
]
