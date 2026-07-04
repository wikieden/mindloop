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
    from tempomem import TempoMem, Verbalizer

    from .execute import CapabilityManifest
    from .phylax import Violation

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
class BindingAmbiguity:
    """A non-fungible multi-candidate object binding (D-I): ask, don't guess.

    ``candidates`` are the close-scoring scene nodes as ``(node_id, label)``.
    The plan is still bound to the top-1 candidate so a clarifier-less brain
    can proceed; a wired Clarifier asks once before dispatch.
    """

    mention: str
    candidates: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Plan:
    """A compiled plan: dispatchable subtasks + a final user-facing utterance."""

    subtasks: tuple[SubTask, ...] = ()
    speak: str = ""
    rationale: str = ""
    # D-I: non-fungible binding ambiguities found at compile time (top-1 bound)
    ambiguities: tuple[BindingAmbiguity, ...] = ()


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
    # Non-empty when the Phylax safety gate (P3) blocked the plan: it was refused,
    # not dispatched (`statuses` is empty), and `plan.speak` carries the refusal.
    violations: tuple[Violation, ...] = ()
    # P7.4 telemetry: which verbalizer tier served ("primary" / "fallback";
    # "" when no mode probe is wired).
    mode: str = ""

    @property
    def blocked(self) -> bool:
        """True if the plan was refused by the safety gate (and not dispatched)."""
        return bool(self.violations)


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
        # the effect encodes WHERE (fix B) so region-relative placement is
        # visible to WorldState / idempotent dispatch
        "eff": ("robot.placed={target}@{location}", "robot.hand=empty"),
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
    # Task-family verbs (TASK-FAMILIES step 1). `{location}` is the second arg
    # (compile fills it; empty when absent). `deliver` is planner-facing — the
    # two-pass macro expansion (D-D) lands with the harness tranche; until then
    # it compiles as a single subtask the mock realizes generically.
    "present": {
        "skill": "present",
        "pre": ("robot.near={target}",),
        "eff": ("robot.presented={target}",),
    },
    "wipe": {
        "skill": "wipe_surface",
        "pre": ("robot.near={target}", "robot.hand=empty"),
        "eff": ("{target}.status=clean",),
    },
    "pour": {
        "skill": "pour_liquid",
        "pre": ("robot.holding={target}",),
        "eff": ("{location}.contains={target}",),
    },
    "dispose": {
        "skill": "dispose",
        "pre": ("robot.holding={target}",),
        "eff": ("{target}.disposed=true", "robot.hand=empty"),
    },
    "sweep": {"skill": "sweep_floor", "eff": ("{target}.status=swept",)},
    "vacuum": {"skill": "vacuum_floor", "eff": ("{target}.status=vacuumed",)},
    "mop": {
        "skill": "mop_floor",
        "eff": ("{target}.status=mopped", "{target}.floor=wet"),
    },
    "warn_wet_floor": {
        "skill": "speak_warning",
        "eff": ("{target}.warned=wet_floor",),
    },
    "restock": {
        "skill": "restock",
        "pre": ("robot.holding={target}",),
        "eff": ("{location}.stocked={target}", "robot.hand=empty"),
    },
    "greet": {
        "skill": "greet",
        "pre": ("robot.near={target}",),
        "eff": ("robot.greeted={target}",),
    },
    "take_order": {
        "skill": "take_order",
        "pre": ("robot.near={target}",),
        "eff": ("robot.order_taken={target}",),
    },
    "offer": {
        "skill": "offer_item",
        "pre": ("robot.holding={target}",),
        "eff": ("robot.offered={target}",),
    },
    "deliver": {  # macro: navigate+offer (D-D expansion lands in T3)
        "skill": "deliver",
        "pre": ("robot.holding={target}",),
        "eff": ("robot.delivered={target}",),
    },
}


# --------------------------------------------------------------------------- #
# D-D pass 0 — macro expansion
# --------------------------------------------------------------------------- #
# Planner-facing macros expand to atomic steps BEFORE binding and the manifest
# gate, so Phylax and the `supported` check see the real work, never the macro.
# Values: (child verb, indices into the macro's args). Single-pass: a child is
# never re-expanded, which lets `mop`'s atomic core keep the same verb name.
_MACROS: dict[str, tuple[tuple[str, tuple[int, ...]], ...]] = {
    "deliver": (("navigate", (1,)), ("offer", (0, 1))),
    "sweep": (("navigate", (0,)), ("vacuum", (0,))),
    "mop": (
        ("warn_wet_floor", (0,)),
        ("navigate", (0,)),
        ("mop", (0,)),
        ("warn_wet_floor", (0,)),
    ),
}


def expand_macros(commands: tuple[Command, ...]) -> tuple[tuple[Command, str | None], ...]:
    """Compile pass 0 (D-D): expand macros into ``(command, macro_parent)`` pairs.

    Atomic commands pass through with ``macro_parent=None``. A macro's params
    (e.g. a skill-card rule) propagate to every child so nothing set upstream
    is lost in expansion.
    """
    out: list[tuple[Command, str | None]] = []
    for cmd in commands:
        spec = _MACROS.get(cmd.verb.lower())
        if spec is None:
            out.append((cmd, None))
            continue
        for child_verb, idxs in spec:
            args = tuple(cmd.args[i] for i in idxs if i < len(cmd.args))
            if idxs and not args:
                # e.g. deliver(item) with no recipient: the navigate child has
                # nowhere to go — compile best-effort, but say so loudly
                _log.warning(
                    "macro %r is missing arg(s) at %s — child %r compiles with no target",
                    cmd.verb.lower(),
                    idxs,
                    child_verb,
                )
            out.append((Command(child_verb, args, dict(cmd.params)), cmd.verb.lower()))
    return tuple(out)


def _resolve_node_id(mem: TempoMem, mention: str) -> int | None:
    """Bind an object mention to its best scene-graph node id (B9), or None."""
    nid, _ = _bind_mention(mem, mention)
    return nid


# A candidate counts as "close in score" to the top hit above this ratio (D-I).
# Build-time constant: query scores are only compared within one result list, so
# a relative ratio is scale-free across keyword/semantic backends.
_CLOSE_RATIO = 0.75


def _has_qualifier(mention: str, label: str) -> bool:
    """True when the mention carries tokens beyond the candidate label ("red cup")."""
    mention_tokens = {t for t in mention.lower().split() if t}
    label_tokens = {t for t in label.lower().split() if t}
    return bool(mention_tokens - label_tokens)


def _bind_mention(mem: TempoMem, mention: str) -> tuple[int | None, BindingAmbiguity | None]:
    """Bind a mention to its top node id + detect non-fungible ambiguity (D-I).

    Queries k=3 and flags ambiguity ONLY when the close candidates are
    semantically non-interchangeable: (1) different labels near-equal in score,
    or (2) a qualified mention that multiple same-label candidates still tie on
    (the qualifier failed to separate them). Generic mention over identical
    items is fungible — bind top-1 silently.
    """
    if not mention:
        return None, None
    result = mem.query(mention, k=3)
    nodes = getattr(result, "nodes", None) or []
    if not nodes:
        return None, None
    top = nodes[0]
    if top.score > 0:
        close = [n for n in nodes if n.score >= top.score * _CLOSE_RATIO]
    else:
        # a zero/negative top score means the backend couldn't rank: every
        # candidate tied at the top is equally (un)informative — treat the tie
        # as close rather than silently trusting position 0
        close = [n for n in nodes if n.score == top.score]
    if len(close) > 1:
        labels = {n.label for n in close}
        if len(labels) > 1 or _has_qualifier(mention, top.label):
            return top.id, BindingAmbiguity(
                mention=mention, candidates=tuple((n.id, n.label) for n in close)
            )
    return top.id, None


def compile_commands(
    commands: tuple[Command, ...],
    mem: TempoMem,
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
    # the manifest's declared param names are the single source for named_params
    # (D-C minimal): zip each verb's spec params with the positional args
    spec_params = {v.name: v.params for v in manifest.verbs}
    batch = uuid.uuid4().hex[:8]
    subtasks: list[SubTask] = []
    speak_parts: list[str] = []
    ambiguities: list[BindingAmbiguity] = []

    for i, (cmd, macro_parent) in enumerate(expand_macros(commands)):
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
        bound: list[int] = []
        for a in cmd.args:
            nid, amb = _bind_mention(mem, a)
            if nid is not None:
                bound.append(nid)
            if amb is not None:
                ambiguities.append(amb)
                _log.info(
                    "binding ambiguity for %r: candidates %s (bound top-1)",
                    a,
                    amb.candidates,
                )
        target_ids = tuple(bound)
        target_str = cmd.args[0] if cmd.args else ""
        # `{location}` in pre/eff templates is the second arg (place's region
        # anchor, pour's container, restock's destination) — empty when absent
        location_str = cmd.args[1] if len(cmd.args) > 1 else ""
        # table defaults first, then upstream command params (skill-card rules) win
        params = {**meta.get("params", {}), **cmd.params}
        named = {k: a for k, a in zip(spec_params.get(verb, ()), cmd.args, strict=False) if a}
        subtasks.append(
            SubTask(
                id=f"{batch}-{i:02d}",
                verb=verb,
                target_node_ids=target_ids,
                params=params,
                named_params=named,
                skill=str(meta.get("skill", "")),
                preconditions=tuple(
                    p.format(target=target_str, location=location_str) for p in meta.get("pre", ())
                ),
                effects=tuple(
                    e.format(target=target_str, location=location_str) for e in meta.get("eff", ())
                ),
                timeout_s=float(meta.get("timeout", 30.0)),
                macro_parent=macro_parent,
            )
        )

    speak = " ".join(speak_parts)
    if subtasks and not speak:
        speak = default_speak
    return Plan(subtasks=tuple(subtasks), speak=speak, ambiguities=tuple(ambiguities))
