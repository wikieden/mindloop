> 🌐 **English** · [中文](../../zh/devplan/DEV-PLAN.md)

# mindloop L3 Brain — Development Plan

**Scope:** build out the L3 cognitive brain (`mindloop`) from today's
question-answer loop into the full S2 orchestrator the ratified decisions
describe. **L1/L2 (execution, real bodies) are deferred — their design reuses
Brain2Robot's existing L2/L1 work** (owner, 2026-06-15). `bodylink`'s `MockBody`
stands in for a body throughout L3 development.

**Authority:** decisions D1–D5 + K1–K3 (brain-architecture.md §9, ratified
2026-06-15) and body-contract B1–B10 (§11, ratified 2026-06-11). Every phase
**consults the corresponding Brain2Robot design doc first** (standing directive
— B2R is the prototype product).

**Status:** plan v1, 2026-06-15. No code is written for a phase until its spec
is approved.

---

## 0. Principles (apply to every phase)

- **L3 only.** mindloop owns S2 (intent → plan → replan → dialogue) + the
  Phylax policy tier + the protocol seams. Execution, symbolic-BT safety, and
  real bodies stay out (D1) — reuse B2R / defer to `bodylink`.
- **Brain stays stdlib-only at core.** Heavy deps (LLM client, encoders) sit
  behind extras or external endpoints. Same contract as today.
- **Network-free tests.** Every phase tests against `ScriptedReasoner` +
  `MockBody` + hash encoders — never a real LLM or model download.
- **Grounded + audited.** Plans bind object slots to scene-graph node ids;
  answers cite node ids; every decision lands in the L4 trace. The
  pixel → actuator audit chain never breaks (B9).
- **Consult B2R first.** Each phase names the B2R doc it ports; absorb its
  mechanism unless explicitly superseded by a ratified decision.
- **Bilingual docs, Conventional Commits, CHANGELOG per change, CI matrix,
  ruff + pyright gates** — same engineering standard as tempomem core.

---

## 1. Current state (baseline)

| Capability | Status | Where |
|---|---|---|
| `Brain.ingest` (remember) | ✅ shipping | `brain.py` |
| `Brain.ask` (retrieve → reason → cited Answer) | ✅ shipping | `brain.py` |
| `Reasoner` / `Verbalizer` protocols + Scripted / Verbalizer / CosmosReason | ✅ shipping | `reason.py`, `verbalizers.py` |
| `ExecutorAdapter` protocol + `SubTask` / `StatusUpdate` / `CapabilityManifest` + typed `ErrorCode` / `RecoveryHint` | ✅ **P0 done** | `execute.py` |
| `PreferenceStore` (L5) stub + `HealthReport` (B5) + `Brain.health()` | ✅ **P0 done** | `preference.py`, `health.py`, `brain.py` |
| `MockBody` reference executor + `bodylink` package | ✅ **P0 done** | `bodylink/` |

P0 is complete: the executor seam (D1/D3) lives in `execute.py` (open-vocabulary
verbs, node-id-carrying `SubTask` (B9), typed `ErrorCode`/`RecoveryHint` (B3),
two-tier `CapabilityManifest` (D3)), and the `bodylink` member ships `MockBody`
to fill it. Everything below P0 is **net-new** L3 capability — **P1 is next**.

---

## 2. Phase map

```
P0 contracts ─► P1 intent+plan ─► P2 Episteme ─► P3 Phylax ─► P4 trace+replan ─► P5 full loop ─► P6 production
   (seam)         (S2 spine)       (skills)       (policy)      (memory+repair)    (dialogue)      (real LLM+eval)
```

| Phase | Theme | Milestone |
|---|---|---|
| P0 | Seam contracts + test scaffolding | — (mostly done) |
| P1 | Intent routing + planning skeleton | **M-L3.1** |
| P2 | Episteme skill-card library | **M-L3.2** |
| P3 | Phylax policy tier | M-L3.2 |
| P4 | L4 Trace + replanning | **M-L3.3** |
| P5 | Dialogue + full S2 loop | M-L3.3 |
| P6 | Production reasoner + eval + cloud bootstrap | **M-L3.4** |
| P7 | Edge fallback — on-body offline AI chain (LLM + ASR + TTS) | **M-L3.6** |

---

## 3. Phases

### P0 — Seam contracts & test scaffolding  ·  ✅ DONE (2026-06-16)

**Goal:** freeze the protocols L3 plans against, so phases P1+ are pure brain
logic.

- ✅ `ExecutorAdapter` protocol + value types (`SubTask`, `StatusUpdate`,
  `CapabilityManifest`/`BodyProfile`/`VerbSpec`, `TaskStatus`/`ErrorCode`/
  `RecoveryKind`/`RecoveryHint`) — `execute.py`. Open-vocab verbs (D3), node-id
  carry + echo (B9), typed errors/recovery (B3), two-tier manifest (D3).
- ✅ `PreferenceStore` protocol stub (L5, D2) — `preference.py`, provisional.
- ✅ `HealthReport` + `Brain.health()` (B5) — `health.py`, `brain.py`.
- ✅ `bodylink` workspace member created (D5, 4th package) + registered in root
  `pyproject.toml` (`[tool.uv.workspace]` + `[tool.uv.sources]`). `MockBody`
  reference `ExecutorAdapter` + `g1d_manifest()` (B10) + `UnsupportedVerbError`.
  Builds + installs in the workspace (`uv sync`).
- ✅ Contract tests: `mindloop/tests/test_execute.py` (seam value types) +
  `bodylink/tests/test_mock_body.py` (dispatch round-trip, node-id echo,
  typed-failure recovery, runtime-checkable conformance, verb gating).

> `bodylink` is a **workspace-tracked directory** for now (root repo), not yet
> its own GitHub repo/submodule like the other three. It graduates to its own
> repo before publish (needs owner go-ahead — creating a repo is an outward
> action). Noted so the deviation isn't silent.

**B2R ref:** `code_framework.md`, `system_integration.md`,
`embodiment_adaptation.md` (Body Profile tier).
**Tests:** seam value-type contract + MockBody dispatch round-trips — done.
**Verify:** local **189 passed, 2 skipped · ruff clean · pyright 0** (tempomem +
mindloop + worldsense + bodylink). RTX PRO cross-check pending (host was offline
at P0 close; it was a proven dev env earlier at 176 tests).
**Exit:** all seam protocols frozen ✅; `bodylink` builds + installs ✅; node-id
+ typed-error contract locked ✅.

### P1 — Intent routing + planning skeleton  ·  ✅ DONE (2026-06-26)  ·  M-L3.1

**Spec:** [specs/P1-intent-planning.md](specs/P1-intent-planning.md) (B2R-MVP
two-stage format). **Goal:** turn `Brain` from a Q&A box into a router + planner.

- `IntentRouter` — classify an instruction into `{task, question, chat}`.
- `Planner` — task intent → a `list[SubTask]` of **skill verbs**; query the
  body's `CapabilityManifest`, **refuse to emit any verb the body lacks** (D3).
- `Brain.handle(instruction)` — orchestrate: route → (`ask` | plan + dispatch |
  chat); bind object slots to node ids (B9).

**B2R ref:** `l3/intent_router.py`, `l3/task_planner.py`, `psyche_layer.md`.
**Tests (ScriptedReasoner + MockBody):** "bring the bottle on the table" →
`[navigate, pick]` plan, all slots cited; an unsupported verb → refused, not
emitted.
**Exit:** a household instruction produces a verb plan dispatched to MockBody
with every object slot carrying a node id. ✅ Met — `plan.py` + `Brain.handle`;
8 network-free tests; full suite 197 passed; ruff clean; pyright 0.
Cross-validated end-to-end against a live Cosmos-Reason2 vLLM endpoint
(intent routing + LLM verb plan → node-bound dispatch + cited question answer).

### P2 — Episteme skill-card library  ·  M-L3.2  ·  D3/§5, K2  ·  ✅ DONE

**Goal:** procedural knowledge as data — cooking / fabric-aware laundry.
**Done (2026-06-28):** `episteme.py` — see [specs/P2-episteme-skill-cards.md](specs/P2-episteme-skill-cards.md).

- `SkillCard` schema — **flat steps + rules (K2)**; DAG reserved via schema
  version. Fields: `id`, `category`, `preconditions`, `rules`, `steps`,
  `failure_hints`, `safety`, `provenance`.
- YAML card loader + **semantic retrieval** over the library.
- Instantiation: bind category → node ids, resolve rules, overlay L5
  preferences, check manifest → expand to verb sequence.
- No-card → LLM general-knowledge fallback, flagged low-confidence.

**B2R ref:** `techne_crystallization.md`, `household_task_taxonomy.md`,
`appliance_interaction.md`.
**Tests:** `laundry_basic` + a cooking card → verb plans; wool/dark-color rules
resolve to correct program; missing card falls back flagged.
**Exit:** laundry + cooking cards run end-to-end against MockBody.

### P3 — Phylax policy tier  ·  M-L3.2  ·  D4 top tier (semantic)  ·  ✅ DONE

**Done (2026-06-28):** `phylax.py` — see [specs/P3-phylax-policy.md](specs/P3-phylax-policy.md).

**Goal:** the portable, brain-side safety tier (the other two Phylax tiers —
symbolic-BT in `bodylink`, reflex in firmware — are deferred).

- Declarative policy config: forbidden zones, human-proximity speed cap, action
  whitelist, role-based permission gating.
- Policy-check gate between plan and dispatch; every plan passes before it goes
  out.
- Safety-class handling: stop + speak, **no reroute, no retry**.
- Community skill cards are untrusted: signature + review gate before a card
  with `safety:` annotations is honored.

**B2R ref:** `safety_architecture.md` (port §2 L3 hard-constraints, §8
permissions, §9 arbitration; **"upper layer's want-to never overrides lower
layer's must-not"**).
**Tests:** blade op by non-adult → rejected; over-speed near human → rejected;
unsigned `safety:` card → refused.
**Exit:** every dispatched plan has passed a policy check; violations blocked +
traced.

### P4 — L4 Trace + replanning  ·  M-L3.3  ·  D2 + B3

**Goal:** episodic memory + failure-driven repair.

- **L4 Trace store in tempomem core** (D2) — episodic: plans, outcomes, policy
  decisions; every record cites scene node ids (shared id space). *Cross-repo:
  needs a tempomem core change — coordinate with the core changelog.*
- `Replanner` — a failed `StatusUpdate` (typed `ERR_*`, B3) → replan using the
  skill card's `failure_hints` + typed adjustment vocabulary
  (`position_offset`, `orientation_relax`, `force_adjustment`).

**B2R ref:** `trace_memory.md`, the negation-driven-replanning loop in
`L3_cognition.md`.
**Tests:** grasp failure → replan with adjustment; the L4 trace records both
attempts, queryable by node id.
**Exit:** a failed dispatch triggers a bounded replan; L4 trace is queryable
and cited.

### P5 — Dialogue + full S2 loop  ·  M-L3.3

**Goal:** the complete cognitive loop, end-to-end, against MockBody.

- Dialogue engine — memory-grounded chat (extends `ask`); multi-turn context.
- Full loop wired: instruction → route → plan → policy → dispatch → status →
  replan → trace.
- L5 `PreferenceStore` overlay — preferences modify card defaults per person.

**B2R ref:** `05_scenarios/breakfast_e2e.md`, `e2e_walkthrough.md`.
**Tests:** reproduce the B2R breakfast / cleanup scenario against MockBody —
fully cited and traced, no real network.
**Exit:** a B2R end-to-end household scenario runs on the full S2 loop with
MockBody.

### P6 — Production reasoner + eval + cloud bootstrap  ·  M-L3.4  ·  B6

**Goal:** swap ScriptedReasoner for a real LLM; measure; deploy.

- Wire `CosmosReasonVerbalizer` (exists) as the S2 reasoner end-to-end.
- Eval harness: planning accuracy, citation compliance, policy compliance,
  replan success rate (extend tempomem's `bench` + brain `eval`).
- Cloud bootstrap → onboard Thor via `base_url` switch (B6), protocol
  unchanged.

**B2R ref:** `roadmap_techstack.md`, `mvp_plans.md`.
**Tests:** real Cosmos-Reason2 runs the loop; eval suite green against budget
(B2: query 100–500 ms, simple task 0.5–2 s).
**Exit:** production reasoner drives the full loop; eval thresholds met; cloud →
Thor switch verified.

---

### P7 — Edge fallback: on-body offline AI chain  ·  M-L3.6  ·  cross-cutting

**Goal:** when the network is down, stay cognitively functional on-body — a small
local LLM + on-body ASR + TTS form a self-contained AI chain. The remote big
models are primary; the on-body chain is a **degraded fallback**, never losing
safety or memory (both already local). See full spec:
[specs/P7-edge-fallback.md](specs/P7-edge-fallback.md).

- **`FailoverVerbalizer`** — wraps `[remote, on-body]` Verbalizers; on a transport
  error (`QueryError`) falls to the local OpenAI-compatible server, with
  hysteresis. Brain unchanged (reuses the `Verbalizer` seam); covers both Reasoner
  and Planner/IntentRouter.
- **`Listener` (ASR) + `Speaker` (TTS) seams** — new BYO protocols mindloop ships
  (like `ExecutorAdapter`), with `Mock*` impls; a thin `voice.py` loop ties
  `Listener → handle → Speaker`. On-body engines (whisper.cpp/sherpa-onnx; piper)
  are out-of-tree.
- **Mode arbitration** — a `ConnectivityMonitor` picks online (remote) vs offline
  (on-body); degradation contract (skill-card-first, conservative safety, simpler
  answers, honest "I'm offline" UX).

**Owner decisions (spec §7):** degraded-not-parity (D-edge-1); ASR/TTS as new BYO
seams (D-edge-2); the edge LLM/ASR/TTS stack + compute target; ASR/TTS package home.
**Exit (M-L3.6):** pull the network — the robot still hears, plans, passes the
safety gate, acts, and speaks, entirely on its own compute.

---

## 4. Milestones

| Milestone | Phases | Definition of done |
|---|---|---|
| **M-L3.1** | P1 | instruction → cited verb plan → MockBody dispatch |
| **M-L3.2** | P2 + P3 | skill cards run; every plan policy-checked |
| **M-L3.3** | P4 + P5 | full S2 loop with trace + replan; B2R scenario reproduced |
| **M-L3.4** | P6 | real Cosmos-Reason2 + eval green + cloud→Thor |

---

## 5. Cross-cutting & dependencies

- **tempomem core change (P4):** L4 Trace store lands in the core, not mindloop
  — coordinate via the core CHANGELOG; keep the numpy-only contract.
- **Body team asks (`body-team-asks-v0.md`):** `/l2/capabilities`, world-frame
  detections, node-id seam, typed errors. **MockBody unblocks all of L3
  meanwhile** — real-body integration waits on those answers.
- **Encoder for Episteme retrieval (P2):** semantic card search needs an
  encoder; hash encoder for tests, real encoder behind an extra.
- **Naming (architecture §10):** Psyche / Episteme / Phylax / Hexis — confirm
  before they become public module names.

## 6. Risks

| Risk | Mitigation |
|---|---|
| L4 Trace couples mindloop ↔ tempomem core | land L4 in core first (P4 gated on a core release) |
| Episteme retrieval quality | start rule-first; semantic search additive |
| Cosmos-Reason2 latency vs B2 budget | cloud bootstrap; measure in P6 eval before Thor |
| Policy completeness (no FMEA yet) | enumerate from B2R hard-constraints; FMEA an inherited open item |
| Scope creep into L2/L1 | hard line — deferred, reuse B2R; MockBody is the only body in L3 dev |

---

## 7. Sequencing

P0 → **P1** → (P2 ∥ P3) → P4 → P5 → P6. P2 and P3 can proceed in parallel once
P1 lands (cards need the planner; policy wraps the planner — independent).
P4's L4-in-core dependency is the one cross-repo gate; start the core change
early.

*Plan v1, 2026-06-15. Spec each phase before coding; verify before claiming
done.*
