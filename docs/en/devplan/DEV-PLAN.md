> 🌐 **English** · [中文](../../zh/devplan/DEV-PLAN.md)

# mindloop L3 Brain — Development Plan

**Scope:** build out the L3 cognitive brain (`mindloop`) from a question-answer
loop into the full S2 orchestrator the ratified decisions describe. **L1/L2
(execution, real bodies) are deferred — their design reuses Brain2Robot's existing
L2/L1 work** (owner, 2026-06-15). `bodylink`'s `MockBody` (and now a Genesis sim
backend) stands in for a body throughout L3 development.

**Authority:** decisions D1–D5 + K1–K3 (brain-architecture.md §9, ratified
2026-06-15) and body-contract B1–B10 (§11, ratified 2026-06-11). Every phase
**consults the corresponding Brain2Robot design doc first** (standing directive —
B2R is the prototype product).

**Status (updated 2026-06-28):** P0–P5 shipped + P7.1 shipped. **M-L3.1 ✅,
M-L3.2 ✅, M-L3.3 ✅** (full S2 loop reproduced e2e). Each phase is spec'd before
coding and verified before "done". Brain suite: 85 network-free tests, ruff clean,
pyright 0.

---

## 0. Principles (apply to every phase)

- **L3 only.** mindloop owns S2 (intent → plan → replan → dialogue) + the Phylax
  policy tier + the protocol seams. Execution, symbolic-BT safety, and real bodies
  stay out (D1) — reuse B2R / defer to `bodylink`.
- **Brain stays stdlib-only at core.** Heavy deps (LLM client, encoders) sit behind
  extras or external endpoints.
- **Network-free tests.** Every phase tests against `ScriptedReasoner` + `MockBody`
  + hash encoders + injected fakes — never a real LLM or model download.
- **Grounded + audited.** Plans bind object slots to scene-graph node ids; answers
  cite node ids; every dispatch lands in the L4 trace. The audit chain never breaks
  (B9).
- **Consult B2R first.** Each phase names the B2R doc it ports.
- **Bilingual docs, Conventional Commits, CHANGELOG per change, ruff + pyright
  gates** — same standard as tempomem core.

---

## 1. Current state

**Brain spine complete through P4.** `Brain.handle` runs route → plan → compile
(D3 gate) → policy (P3 gate) → dispatch → bounded replan (P4), every step traced.

| Capability | Status | Where |
|---|---|---|
| `Brain.ingest` / `Brain.ask` (cited Answer) | ✅ shipping | `brain.py` |
| `Reasoner`/`Verbalizer` protocols + Scripted/Verbalizer/CosmosReason + **`FailoverVerbalizer`** | ✅ | `reason.py`, `verbalizers.py` |
| Executor seam: `SubTask`/`StatusUpdate`/`CapabilityManifest` + typed `ErrorCode`/`RecoveryHint` | ✅ P0 | `execute.py` |
| Intent routing + two-stage planning (LLM verbs → rule compile) | ✅ **P1 / M-L3.1** | `plan.py` |
| Episteme skill-card library | ✅ **P2** | `episteme.py` |
| Phylax semantic policy tier | ✅ **P3** | `phylax.py` |
| L4 trace + bounded replanning | ✅ **P4** | `trace.py`, `replan.py` |
| Multi-turn dialogue + L5 preference overlay (full loop reproduced e2e) | ✅ **P5 / M-L3.3** | `dialogue.py`, `preference.py`, `brain.py` |
| Reasoner/planner LLM failover (offline AI chain, step 1) | ✅ **P7.1** | `verbalizers.py` |

**Next:** **P6** (swap ScriptedReasoner for the production Cosmos-Reason2 + an eval
harness; cloud→Thor switch). P7.2+ and the D3 body track run in parallel.

> **Parallel D3 body-adaptation track** (in `bodylink`, not this brain plan):
> multi-model manifest catalog (g1d/h1/gr1/arm6), `BaseExecutorAdapter` SDK,
> conformance kit, and a Genesis physics-sim backend (verified host + mac) all
> shipped. Real-hardware adapter + the symbolic-BT/reflex Phylax tiers are pending.
> See [TECH-DESIGN](../../../../docs/en/TECH-DESIGN.md) and
> [bodylink multi-model design](../../../../bodylink/docs/en/multi-model-adaptation-design.md).

---

## 2. Phase map

```
P0 ✅ ─► P1 ✅ ─► P2 ✅ ─► P3 ✅ ─► P4 ✅ ─► P5 ✅ ─► P6 ▢          P7 ▢ (P7.1 ✅)
 seam     S2 spine  skills   policy  trace+   full     production    edge fallback
                                     replan    loop     (LLM+eval)    (offline chain)
```

| Phase | Theme | Milestone | Status |
|---|---|---|---|
| P0 | Seam contracts + test scaffolding | — | ✅ |
| P1 | Intent routing + planning skeleton | M-L3.1 | ✅ |
| P2 | Episteme skill-card library | M-L3.2 | ✅ |
| P3 | Phylax policy tier | M-L3.2 | ✅ |
| P4 | L4 Trace + replanning | M-L3.3 | ✅ |
| P5 | Dialogue + full S2 loop | M-L3.3 | ✅ |
| P6 | Production reasoner + eval + cloud bootstrap | M-L3.4 | ◐ eval + real-LLM drive done; Thor pending HW |
| P7 | Edge fallback — on-body offline AI chain (LLM+ASR+TTS) | M-L3.5 | ◐ P7.1+P7.2 done |

---

## 3. Phases

### P0 — Seam contracts & test scaffolding  ·  ✅ DONE (2026-06-16)

Froze the protocols L3 plans against: `ExecutorAdapter` + value types (`execute.py`,
open-vocab verbs D3, node-id carry/echo B9, typed errors/recovery B3, two-tier
manifest D3), `PreferenceStore` stub (L5), `HealthReport`/`Brain.health()` (B5), and
the `bodylink` member with `MockBody` + `g1d_manifest()` (B10). Contract tests green.

> `bodylink` is a **workspace-tracked directory** (root repo), not yet its own
> GitHub repo/submodule. It graduates before publish (owner go-ahead — an outward
> action). Tracked in §8.

### P1 — Intent routing + planning skeleton  ·  ✅ DONE (2026-06-26)  ·  M-L3.1

**Spec:** [specs/P1-intent-planning.md](specs/P1-intent-planning.md). Two-stage
B2R-MVP format: LLM emits a text verb sequence → `compile_commands` deterministically
fills `SubTask` metadata, binds objects to node ids (B9), refuses verbs the body's
manifest lacks (D3). `IntentRouter` + `Planner` (Verbalizer-backed + Scripted).
`Brain.handle` orchestrates route → ask | plan+dispatch. 8 tests; cross-validated
against a live Cosmos-Reason2 endpoint. **No rule-planning fallback online** (§1a).

### P2 — Episteme skill-card library  ·  ✅ DONE (2026-06-28)  ·  M-L3.2  ·  K2

**Spec:** [specs/P2-episteme-skill-cards.md](specs/P2-episteme-skill-cards.md).
Procedural knowledge as data: `SkillCard` = flat steps + rules (K2; DAG reserved via
`schema_version`). `instantiate()` fires situation-matched rules, overlays L5
preferences, gates verbs on the manifest (D3) → emits the **same `Command` IR** the
LLM planner does. BYO-encoder retrieval; `SkillCardPlanner` is library-first with an
LLM fallback flagged low-confidence. Ships laundry + cooking cards (run e2e vs
MockBody). Needed an `operate_appliance` verb added to the body manifests.

### P3 — Phylax policy tier  ·  ✅ DONE (2026-06-28)  ·  M-L3.2  ·  D4 top tier

**Spec:** [specs/P3-phylax-policy.md](specs/P3-phylax-policy.md). The brain-side
**semantic** safety tier (BT + reflex tiers deferred). A declarative `Policy`
(adult-only verbs, supervised-only verbs, forbidden node ids, human-proximity speed
cap, trusted card provenances) vetted against a `SafetyContext` by `Phylax.check`,
run in `handle()` **between** compile and dispatch. Any violation **blocks the whole
plan** — stop + speak, no reroute/retry (B2R §9 "upper want-to never overrides lower
must-not"). `SkillCardPlanner` refuses untrusted `safety:` cards. Ports B2R
`safety_architecture.md` §2/§8/§9.

### P4 — L4 Trace + replanning  ·  ✅ DONE (2026-06-28)  ·  M-L3.3  ·  D2 + B3

**Spec:** [specs/P4-trace-replanning.md](specs/P4-trace-replanning.md).

- **L4 `TraceStore`** (`trace.py`) — append-only stdlib-sqlite episodic log of every
  attempt + failure, each citing scene node ids (B9); queryable by node/session,
  `failures()` view, never deleted (clear = rotate `session_id`). **Lives in
  `mindloop` for now**; the tempomem-**core** merge envisioned by D2 is deferred to
  a coordinated cross-repo change (tracked in §8) — citing node ids already
  satisfies the shared-id-space requirement.
- **`Replanner`** (`replan.py`) — a typed FAILED `StatusUpdate` (B3) → a **bounded**
  corrective `SubTask` sequence (post-compile, reusing node ids): RETRY / ADJUST
  (offset/relax/force) / REROUTE (navigate + re-issue) / SKIP / ESCALATE. Caps:
  per-(verb, node-ids) ≤2 + global ≤6 → escalate past either (stop + speak, no
  infinite loop). `Brain(replanner=, trace=)` turns dispatch into a bounded replan
  loop; a corrective plan is **re-vetted by Phylax (P3)** before acting.

### P5 — Dialogue + full S2 loop  ·  ✅ DONE (2026-06-28)  ·  M-L3.3

**Spec:** [specs/P5-dialogue-full-loop.md](specs/P5-dialogue-full-loop.md). The loop
was already wired through P4; P5 wraps it with **multi-turn dialogue** (`dialogue.py`
— a `Conversation` threads recent turns into `ask` so follow-ups resolve against
prior turns) and an **L5 preference overlay** (`PreferenceStore.all` + a concrete
`DictPreferenceStore`; `Brain.handle(person=)` overlays a person's preferences onto
the compiled plan's params, manifest-gated, post-compile). `Brain.converse` runs a
turn + records it. **Closes M-L3.3** with an end-to-end scenario test: one
conversation through question → task-success → task-replan→recover →
task-safety-blocked, fully cited + traced, no real network.

### P6 — Production reasoner + eval + cloud bootstrap  ·  ◐ (eval harness done)  ·  M-L3.4  ·  B6

**Goal:** swap ScriptedReasoner for a real LLM; measure; deploy.

- **✅ Eval harness** (`eval.py`, network-free) — `run_eval` scores planning
  accuracy, policy compliance, replan success, citation compliance against scripted
  scenarios; `EvalThresholds` proposes pass bars (§8). The objective scaffolding is
  in place; it runs against any wired reasoner.
- **✅ Real-LLM drive validated (2026-06-28)** — the full S2 loop ran end-to-end
  against the production models on the RTX PRO 6000 host: **Cosmos-Reason2-8B**
  (:8002) as the reasoner + **Qwen3.6-27B** (:8001, thinking off) as the
  planner/router, MockBody as the body. Bilingual tasks produced correct
  node-bound verb plans dispatched to SUCCESS with language-matched `speak`;
  questions answered with cited node ids. **Latency within the B2 budget** —
  question avg 0.41 s (budget 0.1–0.5 s), task avg 0.75 s (budget 0.5–2 s). The
  eval harness's citation metric surfaced a real weakness: Cosmos under-cites on
  some English questions (validity 0.5) — a model-quality finding, not a code bug.
- **▢** Cloud bootstrap → onboard Thor via `base_url` switch (B6) — needs hardware.

Latency budget (B2): query 100–500 ms, simple task 0.5–2 s. **Met.**

**Exit:** production reasoner drives the full loop; eval thresholds met; cloud → Thor
switch verified.

---

### P7 — Edge fallback: on-body offline AI chain  ·  ◐ (P7.1 done)  ·  M-L3.5  ·  cross-cutting

**Spec:** [specs/P7-edge-fallback.md](specs/P7-edge-fallback.md). When the network
drops, stay cognitively functional on-body — a small local LLM + on-body ASR + TTS
form a self-contained chain. Remote big models are primary; on-body is a **degraded
fallback**, never losing safety or memory (both already local).

- **P7.1 ✅** — `FailoverVerbalizer`: wraps `[remote, on-body]` Verbalizers; falls to
  the local server on `QueryError` with call-based hysteresis. Reuses the
  `Verbalizer` seam → covers Reasoner + Planner/IntentRouter, **no brain change**.
- **P7.2 ✅** — `Listener` (ASR) + `Speaker` (TTS) BYO seams + `Mock*` + a thin
  `voice.py` `VoiceLoop` (hear→think→speak). Network-free.
- **P7.3 ▢** — wire the chosen edge stack (**Qwen-aligned**: Reasoner=Cosmos-Reason2,
  Planner=Qwen3.x-8B, ASR=Qwen3-ASR, TTS=Qwen3-TTS) on Jetson Thor/Orin; validate.
- **P7.4 ▢** — degradation contract + mode telemetry + "I'm offline" UX.

**Open owner decisions (spec §7):** degraded-not-parity (D-edge-1); ASR/TTS as new
BYO seams (D-edge-2). **Edge stack: decided Qwen-aligned.**

---

## 4. Milestones

| Milestone | Phases | Status | Definition of done |
|---|---|---|---|
| **M-L3.1** | P1 | ✅ | instruction → cited verb plan → MockBody dispatch |
| **M-L3.2** | P2 + P3 | ✅ | skill cards run; every plan policy-checked |
| **M-L3.3** | P4 + P5 | ✅ | full S2 loop with trace + replan; e2e scenario reproduced |
| **M-L3.4** | P6 | ▢ | real Cosmos-Reason2 + eval green + cloud→Thor |
| **M-L3.5** | P7 | ◐ (P7.1 ✅) | pull the network — robot still hears, plans, gates, acts, speaks on-body |

---

## 5. Cross-cutting & dependencies

- **L4 Trace placement (P4):** built in `mindloop` (`trace.py`), citing node ids.
  The D2 vision of merging it into the tempomem **core** is **deferred** — see §8.
- **Body team asks (`body-team-asks-v0.md`):** `/l2/capabilities`, world-frame
  detections, node-id seam, typed errors. **MockBody + the Genesis sim unblock all
  of L3 meanwhile** — real-body integration waits on those answers.
- **Encoder for Episteme retrieval (P2):** BYO encoder (hash for tests); a real
  encoder behind an extra is still optional/unwired in mindloop.
- **Naming (architecture §10):** Psyche / Episteme / Phylax / Hexis — **adopted**:
  `episteme.py` + `phylax.py` shipped as module names (the "confirm first" gate is
  treated as resolved; flag in §8 if the owner wants to revisit).

## 6. Risks

| Risk | Mitigation / status |
|---|---|
| L4 Trace ↔ tempomem core coupling | **resolved by deviation** — built in mindloop citing node ids; core merge deferred (§8), no core release gating P4 |
| Episteme retrieval quality | rule-first; semantic search additive (shipped BYO-encoder) |
| Cosmos-Reason2 latency vs B2 budget | measure in P6 eval before Thor |
| Policy completeness (no FMEA yet) | enumerated from B2R hard-constraints; **FMEA still open** (§8) |
| Scope creep into L2/L1 | hard line — MockBody/sim is the only body in L3 dev |

---

## 7. Sequencing

`P0 → P1 → (P2 ∥ P3) → P4 → P5 → P6`, with **P7 cross-cutting** (P7.1 landed early
on owner request; P7.2–7.4 gated on the open §7-spec decisions). The D3
body-adaptation track runs in parallel in `bodylink`. **P5 closed M-L3.3** (the
first full-loop integration proof); **P6 is the critical-path next step** (real
reasoner + eval).

---

## 8. Open items & decision log

| Item | State | Note |
|---|---|---|
| **D2: L4 trace → tempomem core merge** | deferred (2026-06-28) | built in mindloop; core merge is a future coordinated cross-repo change. Don't lose this. |
| **Module naming** (Episteme/Phylax/Hexis) | adopted | shipped as module names without a separate owner sign-off; revisit if undesired |
| **Phylax FMEA** | open (inherited) | policy enumerated from B2R hard-constraints, not from a failure-mode analysis |
| **P6 eval thresholds** | proposed | `EvalThresholds` defaults: planning ≥0.9, policy =1.0, replan ≥0.8, intent ≥0.95 — owner to ratify |
| **negation_constraints SubTask field** | not added | P4 didn't need it; add if full B2R replan parity is wanted |
| **bodylink → own repo/submodule** | ✅ done (2026-06-29) | wikieden/bodylink (private) + root submodule, like mindloop/tempomem/worldsense |
| **voicelink speech member** | ✅ done (2026-06-29) | 6th member: ASR/TTS engine fills for the `Listener`/`Speaker` seams (P7); in-root for now |
| **D3 body track** (real HW adapter, BT/reflex Phylax tiers) | pending | tracked in bodylink design doc + TECH-DESIGN, not phased here |
| **Dynamic scene context** (active perception) | ✅ phases 1–4 done | seam + `WorldState` write-back + idempotent dispatch + active-perception tail re-plan — the perceive-act-update cycle is closed; see research/dynamic-scene-context.md |

---

*Updated 2026-06-28. Spec each phase before coding; verify before claiming done.*
