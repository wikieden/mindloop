# Changelog

All notable changes to mindloop (the L3 brain for Chronotope) are documented
here. Format follows [Keep a Changelog](https://keepachangelog.com/); versions
follow SemVer (pre-1.0, the API may change between minor releases).

## [Unreleased]

### Added

- **Idempotent dispatch (dynamic-scene, phase 3)** — `Brain._dispatch_plan` skips a
  subtask whose `effects` the `WorldState` already satisfies (e.g. a replan
  re-issued an already-done `grasp`), returning a synthetic "already satisfied"
  SUCCESS without re-dispatching. Open-world + conservative: a step with no effects
  or any unparseable effect is never skipped (only positively-confirmed outcomes
  skip). Realizes the B2R e2e §P1 idempotency lesson systemically, using the P2
  world-state version as the staleness gate. No false skips — distinct/no-effect
  steps still dispatch.
- **Effect write-back / `WorldState` overlay (dynamic-scene, phase 2)** —
  `world_state.py`: a fast symbolic `predicate → value` layer on top of the
  perceptual map. When a `SubTask` succeeds, its `effects` (`robot.holding=apple`,
  `fridge.status=open`) are written to `Brain.world` and injected into the next
  inference context (`WORLD STATE` block), so a multi-step task stays grounded
  **without re-perceiving every step** — the cheap half of the dynamic-scene loop.
  Closes D4's carried-but-unapplied effects into a symbolic loop **without a
  tempomem-core change** (two layers: tempomem = slow perceptual truth, `WorldState`
  = fast prediction; active perception reconciles them later). `apply` bumps a
  version only on change; `reset` for a new task. `Brain(world_state=…)` opt-in,
  default auto-wired; written back at the single `_record` point (covers dispatch +
  replan). See docs/research/dynamic-scene-context.md §2a.
- **`SceneContextProvider` seam (dynamic-scene, phase 1)** — `scene_context.py`:
  factors the read path (`query` → `serialize`) out of `Brain.ask` /
  `Brain._plan_context` into a seam — `context(Focus, *, k, max_tokens) -> (text,
  version)` — so the *when/how-much* of scene context can later evolve (active
  perception, version-gated re-query) with no orchestration change. `Focus` carries
  the query + plan `node_ids` to keep in view + the robot region. **Behavior-
  preserving:** `DefaultSceneContextProvider` reproduces today's context exactly;
  the map `version` is plumbing (advances on `bump()`, which `Brain.observe`/
  `ingest` now call after a perception write) for the later focus-gated re-serialize.
  First step of the design in docs/research/dynamic-scene-context.md. `Brain(
  context_provider=…)` is opt-in; the default is wired automatically.
- **Voice seams + loop (P7.2, edge fallback)** — `voice.py`: `Listener` (ASR) +
  `Speaker` (TTS) BYO protocols (the ears + mouth, same pattern as
  `ExecutorAdapter`), with `MockListener`/`MockSpeaker` doubles, and `VoiceLoop`
  that ties them to `Brain.converse` (hear → think → speak) over a shared
  `Conversation`. A silent transcription is a no-op (the brain never acts on a
  misheard nothing); the spoken reply is the `Answer` text or the plan's `speak`
  (incl. a Phylax refusal). Network-free — audio is opaque `bytes`, mocks script
  the transcript / record utterances; real on-body engines (whisper.cpp /
  sherpa-onnx; piper / Qwen3-TTS) stay out-of-tree (P7.3). Realizes the recommended
  D-edge-2 design (additive/reversible; owner ratification stands open).
- **Scenario eval harness (P6, network-free half)** — `eval.py`: `run_eval(brain,
  cases)` scores the brain's behavior against scripted `EvalCase`s with no real LLM,
  on the four metrics the dev plan names — **planning accuracy** (dispatched verb
  sequence matches), **policy compliance** (Phylax blocks exactly what should be),
  **replan success** (recoverable failures recover), and **citation compliance**
  (existing). `EvalReport` scores each dimension independently (an un-exercised
  dimension passes vacuously) and lists mismatches for triage; `EvalThresholds` are
  the proposed pass bars (planning ≥0.9, policy =1.0, replan ≥0.8, intent ≥0.95 —
  owner to ratify). The real-Cosmos drive + cloud→Thor switch (the rest of P6) need
  the host endpoint / hardware.
- **Dialogue + full S2 loop (P5, M-L3.3, D2)** — closes M-L3.3. `dialogue.py`:
  `Conversation` carries turn history; `Brain.converse(instruction, conversation,
  *, person=, safety_context=)` runs `handle` with the recent turns threaded into
  `ask` (a follow-up resolves against prior turns — dialogue-grounded *and*
  memory-grounded) and records the turn. **L5 preference overlay** — `PreferenceStore`
  gains `all(person)` + a concrete `DictPreferenceStore`; `Brain(preferences=…)` +
  `handle(..., person=…)` overlays a person's preferences onto a compiled task
  plan's params **after compile, manifest-gated** (a preference wins over a card
  default but can't inject a param the body doesn't declare), so it applies to LLM
  and skill-card plans alike with no `Planner`-protocol change. The single-turn loop
  is unchanged; dialogue + preferences are opt-in. Validated by an end-to-end
  scenario test (one conversation: question → task-success → task-replan→recover →
  task-safety-blocked, fully cited + traced, no network). See
  docs/devplan/specs/P5-dialogue-full-loop.md.
- **L4 trace + failure-driven replanning (P4, M-L3.3, D2/B3)** — `trace.py` +
  `replan.py`. `TraceStore` is an append-only stdlib-sqlite episodic log of every
  dispatched attempt + failure, each citing tempomem **node ids** (B9) so it is
  queryable by object (`by_node`) and session; records are never deleted
  ("clearing" a task rotates the `session_id`), and `failures()` is the
  negation-learning view. `Replanner` maps a typed `FAILED` `StatusUpdate` (B3 —
  `ErrorCode` + `RecoveryHint`) to a **bounded** corrective `SubTask` sequence at
  the post-compile level (reusing node ids): `RETRY` / `ADJUST` (typed offset/
  relax/force param) / `REROUTE` (navigate + re-issue) / `SKIP` / `ESCALATE`. Caps
  are per-`(verb, node-ids)` target (≤2) + a global budget (≤6) — past either it
  escalates (stop + speak, never an infinite loop). `Brain(replanner=…, trace=…)`
  (opt-in) turns dispatch into a bounded replan loop; a corrective plan is
  **re-vetted by Phylax (P3)** before it acts, and an escalation stops the whole
  plan with a repair message. No network, no LLM. See
  docs/devplan/specs/P4-trace-replanning.md.
- **`FailoverVerbalizer` (P7.1, edge fallback)** — a `Verbalizer` that fails over
  from a primary backend to on-body fallbacks: `complete` tries an ordered list of
  `Verbalizer`s and returns the first success; a backend raising `QueryError` (a
  transport failure — network down / server unreachable) is skipped to the next.
  The on-body LLM is just another `CosmosReasonVerbalizer(base_url=localhost)`, so
  this reuses the seam — wrapping the reasoner/planner verbalizer makes the whole
  LLM path failover-capable with **no brain change**. Call-based **hysteresis**
  (deterministic, no wall-clock): a failed primary is demoted to last-resort for a
  `cooldown` of N calls so a flapping link doesn't thrash, then retried; a primary
  success clears it. `mode`/`active_index` expose which backend serves (telemetry),
  `on_switch` fires on a change. First step of P7 (offline AI chain);
  see docs/devplan/specs/P7-edge-fallback.md.
- **Phylax policy tier (P3, M-L3.2, D4 top tier)** — `phylax.py`: the brain-side
  **semantic** safety tier (the symbolic-BT + reflex tiers are deferred). A
  declarative `Policy` (adult-only verbs, supervised-only verbs, forbidden node
  ids, human-proximity speed cap, trusted card provenances) vetted against a
  `SafetyContext` (role/proximity/supervision, conservative defaults) by
  `Phylax.check(plan, context) -> tuple[Violation, ...]`. `Brain(policy=…)` runs
  the gate in `handle()` **between** the manifest-gated compile (D3) and dispatch:
  any violation **blocks the whole plan** — stop + speak, no reroute, no retry
  (D4 §9: "an upper layer's want-to never overrides a lower layer's must-not") —
  and `HandleResult` gains `violations` + `blocked`, with `plan.speak` replaced by
  a refusal and nothing dispatched. Opt-in: no `policy` ⇒ P1/P2 dispatch unchanged.
  `SkillCardPlanner(policy=…)` calls `Phylax.vet_card` to **refuse a `safety:`
  card from an untrusted provenance** before it is honored. Ports Brain2Robot
  `safety_architecture.md` §2/§8/§9. See docs/devplan/specs/P3-phylax-policy.md.
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
