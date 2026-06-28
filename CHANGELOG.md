# Changelog

All notable changes to mindloop (the L3 brain for Chronotope) are documented
here. Format follows [Keep a Changelog](https://keepachangelog.com/); versions
follow SemVer (pre-1.0, the API may change between minor releases).

## [Unreleased]

### Added

- **Episteme skill-card library (P2, M-L3.2, D3/K2)** — `episteme.py`: procedural
  knowledge as data. A `SkillCard` is **flat steps + rules** (K2; a DAG is
  reserved via `schema_version`) — `id`/`category`/`preconditions`/`rules`/
  `steps`/`failure_hints`/`safety`/`provenance`. `instantiate()` expands a card
  into a `Command` sequence: fires the `Rule`s whose `when` slots match the
  situation (e.g. `fabric=wool` → wash `program=delicate`), overlays rule params
  then L5 `preferences` (preferences win, and only set body-declared param keys),
  resolves each step's object slot, and drops verbs the body's manifest does not
  declare (D3). The output is the **same** `Command` IR the LLM planner emits, so
  it flows straight into `compile_commands` (node-id binding B9, SubTask metadata).
  `SkillLibrary.retrieve()` is BYO-encoder (semantic cosine with an `Encoder`,
  else keyword overlap). `SkillCardPlanner` is a `Planner` that plans
  library-first and **falls back to an inner LLM planner flagged low-confidence**
  when no card fits. YAML cards load via `load_cards()` (lazy PyYAML, the
  `skills` extra); cards also build from plain dicts (`SkillCard.from_dict`) so
  tests stay dependency-free. Ships `cards/laundry_basic.yaml` +
  `cards/cook_pasta.yaml`; runs end-to-end against `MockBody`.
- **`Command.params`** — the verb `Command` IR now carries resolved params (a
  skill-card rule's `{"program": "delicate"}`); `compile_commands` merges them
  over the per-verb table defaults into the dispatched `SubTask`.
- **Executor seam (P0, D1/D3)** — `execute.py`: the `ExecutorAdapter` protocol
  the brain dispatches against, plus its value types. `SubTask` carries
  open-vocabulary skill verbs + tempomem scene-graph node ids (B9), never joint
  space (D3/B8). `StatusUpdate` reports back with typed `ErrorCode` +
  `RecoveryHint` (B3) and echoes the node ids. `CapabilityManifest` is two-tier
  (D3): a `VerbSpec` verb tier the planner reads + a `BodyProfile` tier the
  executor uses. `dispatch()` streams `StatusUpdate`s (mirrors `/l2/task_status`).
- **`PreferenceStore` protocol stub (L5, D2)** — `preference.py`, provisional.
- **`Brain.health()` + `HealthReport` (B5)** — `health.py`: brain readiness
  mirroring the body team's L3 init checklist.
- **Intent routing + planning skeleton (P1, M-L3.1)** — `plan.py`: the S2 spine.
  `IntentRouter` (task/question/chat) + `Planner` protocols with LLM-backed
  (`Verbalizer*`) and deterministic (`Scripted*`) impls. Planning follows the
  **Brain2Robot MVP two-stage format**: the LLM emits a compact text verb
  sequence (`Command`s), then `compile_commands()` deterministically fills
  `SubTask` metadata from a per-verb table (mirrors B2R `subtask_compiler.py`),
  binds object mentions to scene-graph node ids via `mem.query` (B9), and
  **refuses any verb the body's `CapabilityManifest` does not declare** (D3).
  `SubTask` gains B2R-aligned `skill`/`preconditions`/`effects`/`timeout_s`
  (carried, not brain-enforced — D4). `Brain.handle()` orchestrates
  route → (`ask` | plan → dispatch | chat); `BrainError` in `errors.py`.
  Validated end-to-end against a live Cosmos-Reason2 vLLM endpoint.
- **`CosmosReasonVerbalizer(extra_body=...)`** — merge arbitrary OpenAI-compatible
  request fields into every payload, e.g.
  `{"chat_template_kwargs": {"enable_thinking": False}}` to disable a thinking
  model's chain-of-thought for clean structured output. The recommended P1
  wiring is a strong instruction-follower (Qwen3.6, thinking off) for the
  `Planner`/`IntentRouter` and Cosmos-Reason2 for the physical-reasoning
  `Reasoner`. The planner prompt now mandates a final `speak` line in the user's
  language.
- **`Brain(default_speak=...)` + `compile_commands(default_speak=)`** — a floor
  utterance used when a dispatched task plan has no `speak` line (the LLM omitted
  it). Guarantees user feedback even with a weak instruction follower, so the
  single-model (Cosmos-only) wiring is robust too. Default `"OK."`; override to
  localize.
