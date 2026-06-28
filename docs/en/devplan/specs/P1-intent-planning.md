> 🌐 **English** · [中文](../../../zh/devplan/specs/P1-intent-planning.md)

# P1 spec — Intent routing + planning skeleton (M-L3.1)

**Status:** approved (owner, 2026-06-26). Implements [DEV-PLAN.md](../DEV-PLAN.md) §P1.
**B2R reference:** `l3/intent_router.py`, `l3/task_planner.py`, `l3/subtask_compiler.py`,
`shared/types.py`. The inference-result format **follows the B2R MVP** (owner directive).

## 1. The B2R-MVP format we adopt

B2R MVP plans in **two stages**:

```
LLM → CommandSequence{commands: list[str]}        # compact text verb lines
      ["NAVIGATE counter", "GRASP mug", "SPEAK ok"]
            ↓ compile_to_subtasks()   pure, table-driven, no LLM
      list[SubTask]{ type, target_id, skill, params,
                     preconditions, effects, timeout_s, ... }
```

The LLM emits only a **compact text verb sequence** (intuitive, token-cheap,
schema-stable, hard to hallucinate); a **deterministic compiler** fills the
structured fields (`skill`/`preconditions`/`effects`/`timeout_s`) from a
per-verb table. The sequence ends with a user-facing utterance.

## 1a. Control flow — LLM decides, rules compile (no rule-planning fallback)

The split is **LLM for stage 1, rules for stage 2** — not "LLM with a
rule-based fallback planner". Online, planning is **always** the LLM; the rule
layer is deterministic *post-processing* (schema fill + safety gate), never a
substitute planner. (B2R's "LLM unavailable → hard-coded sequence" path is
**not** carried — we have no canned plan; an empty LLM reply yields an empty
plan, which is safe.)

```
                    instruction
                        │
              ┌─────────▼──────────┐
              │  IntentRouter      │  ◀── LLM   (VerbalizerIntentRouter)
              │  classify()        │      task / question / chat
              └───┬────────────┬───┘
        question/ │            │ task
          chat    │            │
        ┌─────────▼──┐   ┌─────▼──────────┐
        │ ask()      │   │  Planner       │ ◀── LLM   (VerbalizerPlanner)
        │ retrieve→  │   │  plan()        │     emits TEXT verb lines
        │ reason     │   └─────┬──────────┘     "navigate table / grasp mug / speak …"
        │ (LLM)      │         │
        └─────┬──────┘   ┌─────▼──────────────────────────┐
              │          │  compile_commands()            │ ◀── RULES (deterministic)
              │          │  • _VERB_TABLE → skill/pre/eff │     no LLM
              │          │  • mem.query → bind node id B9 │
              │          │  • drop verb ∉ manifest    D3  │
              │          │  • default_speak floor if none │
              │          └─────┬──────────────────────────┘
              │                │ SubTask[]
              │          ┌─────▼──────────┐
              │          │ executor       │  ◀── body seam (MockBody / real)
              │          │ dispatch()     │
              │          └─────┬──────────┘
              ▼                ▼
           Answer          StatusUpdate[]   →   HandleResult
```

**Reads:** Stage 1 = LLM (intent + verb sequence). Stage 2 = rules
(`compile_commands`, pure). The only non-LLM *degradation* anywhere in the stack
is in `tempomem.query` (semantic→keyword when no encoder, BYO contract) — the
**planning chain has none**. The `Scripted*` classes are test doubles only; the
online `Brain` is wired with `Verbalizer*`.

## 2. Three ratified adaptations

| B2R MVP | mindloop P1 | why |
|---|---|---|
| LLM → `CommandSequence` text lines | **adopt verbatim** | token-cheap, stable |
| `compile_to_subtasks()` table-fill | **adopt verbatim** | reliable, no LLM hallucination of metadata |
| `type` is a fixed enum (`KNOWN_VERBS`) | **open-vocab `verb`**, validated against the body's `CapabilityManifest` | D3 — a new body adds verbs without a brain change |
| `target_id: str` (`"mug"`) | bind the object mention to a **scene-graph node id** via `mem.query` at compile time | B9 — `cited_node_ids` audit chain stays closed |
| `preconditions`/`effects` enforced by L3 | **carried as SubTask metadata, NOT enforced by the brain** — the symbolic-BT tier in `bodylink` consumes them | D4 — the brain owns S2 only; BT enforcement is the middle Phylax tier |

## 3. Types

`execute.py` — extend `SubTask` (backward-compatible, all new fields defaulted):

```python
@dataclass(frozen=True, slots=True)
class SubTask:
    id: str
    verb: str
    target_node_ids: tuple[int, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    # B2R-MVP-aligned metadata, filled by the deterministic compiler. The brain
    # carries but does NOT enforce preconditions/effects (D4 — bodylink's BT does).
    skill: str = ""
    preconditions: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    timeout_s: float = 30.0
```

`plan.py` — new module:

```python
Intent = Literal["task", "question", "chat"]

@dataclass(frozen=True, slots=True)
class Command:                      # parsed LLM text line (B2R intermediate)
    verb: str
    args: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class Plan:
    subtasks: tuple[SubTask, ...] = ()
    speak: str = ""                # final user-facing utterance (not dispatched)
    rationale: str = ""

@dataclass(frozen=True, slots=True)
class HandleResult:
    intent: Intent
    answer: Answer | None = None             # question / chat
    plan: Plan | None = None                 # task
    statuses: tuple[StatusUpdate, ...] = ()  # terminal status per dispatched subtask

@runtime_checkable
class IntentRouter(Protocol):
    def classify(self, instruction: str) -> Intent: ...

@runtime_checkable
class Planner(Protocol):
    def plan(self, instruction: str, context: str) -> tuple[Command, ...]: ...
```

Implementations:
- `VerbalizerIntentRouter(verbalizer)` / `VerbalizerPlanner(verbalizer)` — LLM-backed
  (reuse the same `Verbalizer.complete`); parse a compact reply.
- `ScriptedIntentRouter(map)` / `ScriptedPlanner(map)` — deterministic, network-free tests.

## 4. The compiler

```python
def compile_commands(commands, mem, manifest) -> Plan
```

Pure-ish (reads `mem` only to resolve node ids). For each `Command`:
1. `speak` → accumulate into `Plan.speak`, not a subtask.
2. verb **not in `manifest`** → **drop** (refused, never emitted — D3). Logged.
3. else: look up the per-verb metadata table (skill / default params /
   preconditions / effects / timeout); resolve each object-arg → node id via
   `mem.query` (B9) → emit a `SubTask`.

Per-verb table (best-effort enrichment, mirrors B2R `subtask_compiler`):
`navigate`→`navigate_to`, `grasp`→`grasp_object`(pre: near+hand-empty),
`place`→`place_object`(pre: holding), `open_door`→`open_joint`(angle 90),
`detect`→`detect`, `charging`→`charge`. Unknown-but-manifest-supported verb →
empty metadata, still emitted (open-vocab, D3).

## 5. Brain.handle

```python
Brain(mem, reasoner, *, adapter=None, max_tokens=1500,
      router=None, planner=None, executor=None)

def handle(self, instruction: str, *, k: int = 64) -> HandleResult:
    intent = self._router.classify(instruction)
    if intent in ("question", "chat"):
        return HandleResult(intent, answer=self.ask(instruction, k=k))
    # task
    context = <serialize scene, as ask() does>
    plan = compile_commands(self._planner.plan(instruction, context), self._mem,
                            self._executor.capabilities())
    statuses = tuple(_drain(self._executor.dispatch(st)) for st in plan.subtasks) \
               if self._executor else ()
    return HandleResult(intent, plan=plan, statuses=statuses)
```

`router`/`planner`/`executor` are optional (ask-only `Brain` still works);
`handle` raises a clear error if they are unset. `_drain` consumes the
`StatusUpdate` stream to its terminal element.

## 6. Tests (`tests/test_plan.py`, network-free)

- `"bring the bottle on the table"` → `ScriptedPlanner` emits `navigate, grasp,
  speak` → compile → `[navigate, grasp]` SubTasks, each with a node id bound,
  `speak` in `Plan.speak`; MockBody dispatch all terminal `SUCCEEDED`.
- a planned verb **outside** the manifest → dropped, never dispatched (no
  `UnsupportedVerbError`).
- `question` intent → routed to `ask`, returns an `Answer`.
- compiler binds object mentions to the correct node ids; unknown object → empty
  targets (logged), still emitted.

## 7. Files

`execute.py` (extend SubTask) · `plan.py` (new) · `brain.py` (add `handle`) ·
`__init__.py` (exports) · `tests/test_plan.py` (new) · `CHANGELOG.md`.

**Exit (M-L3.1):** a household instruction produces a verb plan dispatched to
MockBody with every object slot carrying a node id; unsupported verbs refused.
