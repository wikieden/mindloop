"""Intent routing + planning (P1, the S2 spine).

Two-stage planning, following the Brain2Robot MVP format (owner directive): an
LLM emits a **compact text verb sequence** (`Command`s, token-cheap and
schema-stable), then a **deterministic compiler** (`compile_commands`) fills the
structured `SubTask` metadata from a per-verb table and binds object mentions to
scene-graph node ids (B9). The compiler refuses any verb the body's
`CapabilityManifest` does not declare (D3). See B2R `l3/task_planner.py` +
`l3/subtask_compiler.py`, and docs/devplan/specs/P1-intent-planning.md.

Network-free by construction: the LLM-backed `Verbalizer*` classes take a BYO
`Verbalizer`; the `Scripted*` classes are deterministic for tests.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from .execute import StatusUpdate, SubTask
from .reason import Answer

if TYPE_CHECKING:
    from tempomem import SpatialMemory, Verbalizer

    from .execute import CapabilityManifest

_log = logging.getLogger("mindloop.plan")

Intent = Literal["task", "question", "chat"]
_INTENTS: frozenset[str] = frozenset(("task", "question", "chat"))


# --------------------------------------------------------------------------- #
# value types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Command:
    """One parsed LLM text line — the B2R intermediate representation.

    ``verb`` is lower-cased; ``args`` are the remaining whitespace tokens (object
    mentions / locations). Not yet validated or node-bound — that is the
    compiler's job.
    """

    verb: str
    args: tuple[str, ...] = ()
    # Verb-specific params resolved upstream (e.g. an Episteme skill card's rule
    # sets ``{"program": "delicate"}``). Empty for a bare text line from the LLM;
    # the compiler merges these over the per-verb table defaults.
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Plan:
    """A compiled plan: dispatchable subtasks + a final user-facing utterance."""

    subtasks: tuple[SubTask, ...] = ()
    speak: str = ""
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class HandleResult:
    """The outcome of `Brain.handle`: an answer (question/chat) or a plan (task).

    For a task with an executor wired, `statuses` holds the terminal
    `StatusUpdate` of each dispatched subtask (in plan order).
    """

    intent: Intent
    answer: Answer | None = None
    plan: Plan | None = None
    statuses: tuple[StatusUpdate, ...] = ()


# --------------------------------------------------------------------------- #
# protocols
# --------------------------------------------------------------------------- #
@runtime_checkable
class IntentRouter(Protocol):
    """Classify a user instruction into a coarse `Intent`."""

    def classify(self, instruction: str) -> Intent: ...


@runtime_checkable
class Planner(Protocol):
    """Turn a task instruction (+ scene context) into a verb `Command` sequence."""

    def plan(self, instruction: str, context: str) -> tuple[Command, ...]: ...


# --------------------------------------------------------------------------- #
# scripted (deterministic, network-free) impls
# --------------------------------------------------------------------------- #
class ScriptedIntentRouter:
    """Deterministic `IntentRouter` for tests: instruction -> intent, else default."""

    def __init__(
        self, intents: dict[str, Intent] | None = None, *, default: Intent = "task"
    ) -> None:
        self._intents: dict[str, Intent] = dict(intents or {})
        self._default: Intent = default

    def classify(self, instruction: str) -> Intent:
        return self._intents.get(instruction, self._default)


class ScriptedPlanner:
    """Deterministic `Planner` for tests: instruction -> a fixed `Command` sequence."""

    def __init__(self, plans: dict[str, tuple[Command, ...]] | None = None) -> None:
        self._plans = dict(plans or {})

    def plan(self, instruction: str, context: str) -> tuple[Command, ...]:
        return self._plans.get(instruction, ())


# --------------------------------------------------------------------------- #
# LLM-backed impls (BYO Verbalizer)
# --------------------------------------------------------------------------- #
_INTENT_PROMPT = (
    "Classify the user instruction into exactly one word: task, question, or chat.\n"
    "- task: asks the robot to physically do something.\n"
    "- question: asks about the world/scene.\n"
    "- chat: smalltalk.\n"
    "Reply with ONLY the one word.\n\nINSTRUCTION: {instruction}\nINTENT:"
)

_PLAN_PROMPT = (
    "You are a household robot planner. Output an executable command sequence, "
    "one command per line, as 'verb arg1 arg2'. Use ONLY the verbs listed in the "
    "context; refer to objects by their scene names. The LAST line MUST be "
    "'speak <one short sentence telling the user what you will do>' — never omit "
    "it, and write the speak sentence in the same language as the instruction. "
    "Output only the command lines, nothing else.\n"
    "Example:\n"
    "navigate table\n"
    "grasp mug\n"
    "speak Sure, I'll bring you the mug.\n\n"
    "CONTEXT:\n{context}\n\nINSTRUCTION: {instruction}\nCOMMANDS:"
)


class VerbalizerIntentRouter:
    """`IntentRouter` backed by a BYO `Verbalizer` (the same LLM as the reasoner)."""

    def __init__(self, verbalizer: Verbalizer, *, prompt_template: str = _INTENT_PROMPT) -> None:
        self._vb = verbalizer
        self._tmpl = prompt_template

    def classify(self, instruction: str) -> Intent:
        reply = self._vb.complete(self._tmpl.format(instruction=instruction)).strip().lower()
        for word in reply.replace("\n", " ").split():
            token = word.strip(".,!:;\"'`")
            if token in _INTENTS:
                return token  # type: ignore[return-value]
        return "question"  # safe default: never silently dispatch a body action


class VerbalizerPlanner:
    """`Planner` backed by a BYO `Verbalizer`: emits a B2R-style verb sequence."""

    def __init__(self, verbalizer: Verbalizer, *, prompt_template: str = _PLAN_PROMPT) -> None:
        self._vb = verbalizer
        self._tmpl = prompt_template

    def plan(self, instruction: str, context: str) -> tuple[Command, ...]:
        reply = self._vb.complete(self._tmpl.format(context=context, instruction=instruction))
        return parse_commands(reply)


def parse_commands(text: str) -> tuple[Command, ...]:
    """Parse a newline-separated verb sequence into `Command`s (B2R text format).

    Each non-empty line becomes ``Command(verb=lower(first token), args=rest)``.
    Bullet/number prefixes are tolerated. A `speak` line keeps its whole message
    as a single arg so the utterance survives compilation.
    """
    cmds: list[Command] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*0123456789. ").strip()
        if not line:
            continue
        parts = line.split()
        verb = parts[0].lower()
        if verb == "speak":
            cmds.append(Command("speak", (line[len(parts[0]) :].strip(),)))
        else:
            cmds.append(Command(verb, tuple(parts[1:])))
    return tuple(cmds)


# --------------------------------------------------------------------------- #
# deterministic compiler  (text Commands -> structured SubTasks, B9 + D3)
# --------------------------------------------------------------------------- #
# Per-verb metadata table, mirroring B2R `subtask_compiler.py`. Best-effort
# enrichment: a verb the body supports but absent here still compiles (open-vocab
# D3) with empty metadata. `{target}` is filled with the first arg.
_VERB_TABLE: dict[str, dict[str, Any]] = {
    "navigate": {
        "skill": "navigate_to",
        "pre": ("robot.canMove",),
        "eff": ("robot.location={target}",),
    },
    "grasp": {
        "skill": "grasp_object",
        "params": {"grasp_type": "side"},
        "pre": ("robot.near={target}", "robot.hand=empty"),
        "eff": ("robot.holding={target}",),
    },
    "place": {
        "skill": "place_object",
        "pre": ("robot.holding={target}",),
        "eff": ("robot.placed={target}", "robot.hand=empty"),
    },
    "open_door": {
        "skill": "open_joint",
        "params": {"angle_deg": 90},
        "pre": ("robot.near={target}", "robot.hand=empty"),
        "eff": ("{target}.status=open",),
    },
    "detect": {"skill": "detect"},
    "charging": {
        "skill": "charge",
        "pre": ("robot.near=charger",),
        "eff": ("robot.charging=true",),
    },
}


def _resolve_node_id(mem: SpatialMemory, mention: str) -> int | None:
    """Bind an object mention to its best scene-graph node id (B9), or None."""
    if not mention:
        return None
    result = mem.query(mention, k=1)
    nodes = getattr(result, "nodes", None) or []
    return nodes[0].id if nodes else None


def compile_commands(
    commands: tuple[Command, ...],
    mem: SpatialMemory,
    manifest: CapabilityManifest,
    *,
    default_speak: str = "",
) -> Plan:
    """Compile a verb `Command` sequence into a `Plan` (the B2R compile stage).

    Deterministic, no LLM. For each command: `speak` accumulates into
    `Plan.speak`; a verb the body does not declare is **dropped** (D3, logged); an
    accepted verb becomes a `SubTask` with per-verb metadata filled and each
    object arg bound to a node id via `mem.query` (B9).

    `default_speak` is the floor utterance: if the plan has subtasks but the LLM
    omitted a `speak` line (weaker instruction-followers like Cosmos-Reason2 do),
    it is used so a dispatched task always has a user-facing acknowledgement.
    """
    supported = manifest.verb_names()
    batch = uuid.uuid4().hex[:8]
    subtasks: list[SubTask] = []
    speak_parts: list[str] = []

    for i, cmd in enumerate(commands):
        verb = cmd.verb.lower()
        if verb == "speak":
            if cmd.args and cmd.args[0]:
                speak_parts.append(cmd.args[0])
            continue
        if verb not in supported:
            _log.warning(
                "planner dropped unsupported verb %r (body=%r supports %s)",
                verb,
                manifest.body_profile.profile_id,
                sorted(supported),
            )
            continue
        meta = _VERB_TABLE.get(verb, {})
        target_ids = tuple(nid for a in cmd.args if (nid := _resolve_node_id(mem, a)) is not None)
        target_str = cmd.args[0] if cmd.args else ""
        # table defaults first, then upstream command params (skill-card rules) win
        params = {**meta.get("params", {}), **cmd.params}
        subtasks.append(
            SubTask(
                id=f"{batch}-{i:02d}",
                verb=verb,
                target_node_ids=target_ids,
                params=params,
                skill=str(meta.get("skill", "")),
                preconditions=tuple(p.format(target=target_str) for p in meta.get("pre", ())),
                effects=tuple(e.format(target=target_str) for e in meta.get("eff", ())),
                timeout_s=float(meta.get("timeout", 30.0)),
            )
        )

    speak = " ".join(speak_parts)
    if subtasks and not speak:
        speak = default_speak
    return Plan(subtasks=tuple(subtasks), speak=speak)
