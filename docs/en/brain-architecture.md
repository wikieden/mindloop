> 🌐 **English** · [中文](../zh/brain-architecture.md)

# Brain Architecture — the three-layer cognitive stack

**Status:** proposal v1 (brainstorm output, 2026-06-11). This is the decision
record for the formal, open-source, multi-device productionization of
Brain2Robot, refactored **into this package**. Decisions D1–D5 and the three
design knobs K1–K3 (§9) **are ratified** (owner, 2026-06-15) — this is now the
authoritative design, though no code is written until an implementation plan is
approved. The body-contract rules in §11 (B1–B10) **are ratified** (owner,
2026-06-11).
**Audience:** contributors shaping the production brain; integrators porting a
new robot body.
**Companion docs:** [cosmos3-tempomem-llm-brain.md](cosmos3-tempomem-llm-brain.md)
(the memory↔reasoning inner loop this stack wraps),
[local-serving.md](local-serving.md) (self-hosting the reasoner),
[post-training-rl-roadmap.md](post-training-rl-roadmap.md) (what to SFT/RL).

## 1. Thesis

A household robot brain is not one model — it is **three loops at three speeds**,
each placed where its latency budget demands:

| Layer | Speed | Does | Runs | Placement |
|---|---|---|---|---|
| **Deliberation** (S2, "Psyche") | slow, ~seconds | intent → plan → replan → dialogue; memory-grounded reasoning | LLM/VLM (BYO, OpenAI-compatible) | cloud at bootstrap → onboard Thor via `base_url` switch, zero protocol change |
| **Habit** (S1) | medium, ~100 ms | skill execution: instantiate skill cards into behaviour-tree plans of skill verbs; monitor; report | BT runtime + memory queries (numpy core is local) | **onboard, fixed** |
| **Reflex** | fast, ~1 ms | e-stop, torque limits, collision reaction | device firmware / realtime controller | **onboard, fixed; per-body** |

The brain package owns Deliberation and the *contracts* the other two layers
fill. Habit's reference runtime and every body live behind protocol seams
(§3). Reflex is a black box the brain reads status from and never drives.

Compute today: **Jetson AGX Thor** = onboard, **RTX PRO 6000 (96 GB)** =
dev/training (LoRA, eval), cloud = bootstrap only.

## 2. The three layers

### 2.1 Deliberation (S2) — what this package is

The cognitive loop already shipping here, extended with planning:

```
user/world event
  → intent routing (task? question? chat?)
  → retrieve: SpatialMemory.query(k) → serialize(node_ids=hits)   # cited context
  → reason: Reasoner (LLM) → plan in skill verbs, or Answer(text, cited_node_ids)
  → policy check (Phylax, §6) → dispatch to Habit via ExecutorAdapter
  → on failure report: replan (failure hints from the skill card, §5)
```

Everything S2 emits is **grounded**: plans bind object slots to scene-graph
node ids; answers cite node ids. The audit chain from camera pixel to actuator
command never breaks.

Absorbed from Brain2Robot (the experimental repo): intent router, task
planner, replanner, dialogue engine — re-implemented against `SpatialMemory`
instead of B2R's hand-rolled scene graph / WorldState.

### 2.2 Habit (S1) — behind the executor seam

Skill-card instantiation produces a BT plan of **skill verbs** (§4). The
reference BT runtime, mock body, and simulators live in a separate workspace
member (`tempomem-exec`, proposed, §3); real bodies (e.g. Unitree G1) are
independent packages implementing the same `ExecutorAdapter`.

### 2.3 Reflex — out of scope, on purpose

Per-body, non-negotiable, onboard. The brain's only interface to it is status
ingestion (for traces and replanning) and configuration *reading*. No brain
code path can loosen a reflex limit.

## 3. Package boundaries (D1, D5)

```
tempomem            core: scene-graph memory (L3) + trace (L4, proposed)   numpy-only
worldsense eyes: RGB-D → world-frame Detections                   [clip] extra
mindloop      THIS: S2 + Episteme skill cards + protocol seams       stdlib core
tempomem-exec       proposed: ExecutorAdapter reference impl (BT + MockBody, Genesis behind [sim])
```

The brain stays stdlib-only in core, exactly like today. It ships **protocols**,
others ship implementations — same move the memory core made with
`PerceptionAdapter` and `Verbalizer`:

| Seam | Protocol (lives here) | Filled by |
|---|---|---|
| execution | `ExecutorAdapter` — dispatch plan, stream status, expose capability manifest | `tempomem-exec`, device packages |
| reasoning | `Reasoner` / `Verbalizer` (existing) | any OpenAI-compatible endpoint |
| preference | `PreferenceStore` (L5, proposed) | external (Mem0 or other) |

What does **not** move into this package: py-trees, Genesis/Isaac, ROS2/Redis
transport, scene assets — B2R's L2/L1/sim/transport stay outside the seam.

## 4. Action interface: skill verbs + two-tier capability manifest (D3, ratified)

The 7-DOF-EE + gripper canonical action space is **dropped as the L3 interface
language, not fixed** — a body may still use it internally inside a VLA skill,
but the brain never speaks it. The brain plans in **skill verbs** (`navigate`,
`pick`, `place`, `open`, `operate_appliance`, …); each device publishes a
**two-tier capability manifest**:

- **verb tier** (brain-facing) — which verbs it supports, parameter domains,
  appliance types. The planner queries it at plan time: a verb the body lacks →
  degrade or refuse, never emit.
- **Body Profile tier** (executor-facing, absorbed from B2R
  `embodiment_adaptation.md`) — DOF/joint table, sensor config, gripper
  mapping, base type; auto-registered from URDF/vendor API at body bring-up.
  Exposed via `/l2/capabilities` (proposed seam; missing in the G1-D spec).

This is B2R's **Soma abstraction** ("swap the body, keep the mind") made into an
engineering fact: a new robot = a new Body Profile + a package implementing the
verb set; the brain changes nothing. The B2R **Action Normalizer** (canonical →
IK → joint angles) and **Sensor Stem** (heterogeneous sensors → fixed-length
tokens, zero-pad missing) stay *inside* the device package, behind the seam —
their cost stays O(n + m) (n skills + m bodies), not O(n × m).

Multi-device support = more manifests, not new geometry. Bimanual, whole-body,
locomotion = more verbs. Joint-space canonicalization is an L1/L2 problem the
brain refuses to own. See §5 (D5) for the per-body package model.

## 5. Episteme — the life-skill knowledge layer

Procedural knowledge (cooking techniques, fabric-aware laundry programs) is
**data, not code, not weights**: declarative **skill cards**.

```yaml
id: laundry_basic_v1
category: laundry
preconditions: {appliances: [washer], verbs: [pick, place, operate_appliance]}
rules:                                  # judgment knowledge
  - if: {fabric: wool}                  → {program: wool, temp: 30, spin: low}
  - if: {color: dark, first_wash: true} → {batch: separate}
steps:                                  # procedural knowledge — categories only, never instance ids
  - sort(clothes, by: rules)
  - load(washer, batch)
  - operate_appliance(washer, program)
failure_hints: [door_blocked → retry_after(open_door)]
safety: [chemicals]                     # Phylax hook, mandatory for heat/blade/chemical cards
provenance: builtin | community | distilled | user_taught
```

Cards reference **categories and affordances only**; binding to real
scene-graph nodes happens at plan time (with `cited_node_ids`). That is what
makes a card portable across homes and bodies.

Runtime: intent → semantic retrieval over the card library (no card → LLM
general knowledge fallback, flagged low-confidence) → S2 instantiates: bind
nodes, resolve rules, overlay L5 preferences, check manifest → expand to verbs
→ execute → trace to L4.

**Extensibility ladder** (the open-source growth engine):
1. drop in a card file — zero code;
2. **skill packs** (versioned bundles declaring required verb set + appliance types) — community distribution;
3. **crystallization**: repeatedly-successful LLM-fallback plans / user corrections in L4 traces → LLM drafts a card → human review → library;
4. LoRA distillation — only for high-frequency skills cards cannot express; last resort, on the RTX box.

Attribute supply: fabric/color/state come from perception Route D (VLM
semantic enrichment → node `attributes`) — the laundry rules are that field's
first real consumer.

## 6. Safety — Phylax, three-tier defense-in-depth (D4, ratified)

Absorbed from B2R `safety_architecture.md`. Three tiers at three timescales; an
upper tier's failure is caught by a lower one. Neural nets may fail (VLM
misjudges, VLA grasps air) but the symbolic net and the realtime layer are
never bypassed by a semantic error.

| Tier | ~Freq | What | Where | Portable? |
|---|---|---|---|---|
| **Policy** (semantic) | ~1 Hz | semantic hard-constraints (human-proximity speed cap, blade ops adult-only, open-flame needs supervision; injected as a KV-fixed segment each plan cycle) + role-based permission gating + **safety-class replan escalation**: a safety error never reroutes or retries — stop immediately, speak | mindloop (S2) | yes — config ships with brain |
| **Symbolic** (BT) | ~5 Hz | BT precondition net (VLA may fail, the symbolic net is not bypassed) + parallel safety nodes (collision → SAFETY_STOP straight to L1, bypassing the BT main sequence and L3) + thermal-safety rules (refuse GRASP/PLACE on a heating vessel until the framework is ready) | bodylink (S1 runtime) | yes — ships with BT runtime |
| **Reflex** (physical) | 1 kHz | SAFETY_STOP hard-stop · torque/velocity limiting · per-body hardware (dual-channel e-stop SIL3, force+ToF+bumper triple-redundant collision, mechanical+software dual limits) | device firmware | no — per-body, brain reads status only |

**Arbitration (verbatim from B2R):** signal priority is `SAFETY_STOP` >
safety-class escalation > permission gating > symbolic precondition net >
thermal/proximity slow-down > normal task. The governing rule — **an upper
layer's "want to" can never override a lower layer's "must not"; the guardian
tightens one-way only (a lower tier can veto an upper, never the reverse).**
The four safety modes (teaching / auto / safe-stop / emergency-stop) live in
the device-side state machine.

Every policy decision and every dispatched plan lands in the L4 trace with the
node ids it touched — audit closes end-to-end. Community skill cards are
untrusted input: signature + review gate before a card with `safety:`
annotations is honored. Inherited open items from B2R: thermal-sensing closed
loop, formal hazard analysis / FMEA, child-permission granularity,
"supervision" detection criteria.

## 7. Memory (D2)

| Layer | What | Where |
|---|---|---|
| L3 scene graph | objects, regions, relations, embeddings | `tempomem` core (shipping) |
| L4 trace (episodic) | plans, outcomes, policy decisions | **into core** (proposed) — traces cite scene node ids; things sharing an id space do not live in separate stores |
| L5 preference | per-person taste, habits, overrides | **out** — `PreferenceStore` protocol; different lifecycle, privacy, per-user isolation |

Write lanes stay single-writer by construction: perception writes detections
(through the fusion arbiter), the brain writes semantic updates (through
`update()`), no new arbitration machinery.

## 8. Perception interface (consumed, not owned)

Dual-rate fusion, single fusion point (the core's arbiter):

- **Route A** fast loop (10–30 Hz, onboard, fixed): open-vocab detection +
  CLIP crop embedding + depth lift → `Detection`. Video tracking
  (`track_id` in `Detection.aux`) as an association prior — knob K1.
- **Route D** slow loop (0.1–1 Hz keyframes, cloud → Thor): VLM → structured
  JSON (state/attributes/affordances). Grounding by **Set-of-Marks**: project
  existing node bboxes into the keyframe labelled `#id`; the VLM answers in
  node ids — no fuzzy re-association, same id language as `cited_node_ids`.

Dedup = the arbiter's four-signal score (distance + 3D-IoU + embedding cos +
label vote) + post-hoc `consolidate()` + `resplit()`. Production gaps tracked:
adjacent same-class instances (mitigated by K1 tracking) and ghost nodes after
object moves (needs frustum negative evidence; Route D "`#id` moved" handles
the rest).

## 9. Decisions — all ratified (owner, 2026-06-15)

| # | Decision | Ruling |
|---|---|---|
| D1 | executor scoping | brain = S2 only = the body team's L3 slot (`/l3/task_execute`); execution behind `ExecutorAdapter`; L2/L1/sim/transport stay out |
| D2 | memory unification | L3 + L4 into `tempomem` core; L5 behind external `PreferenceStore` protocol |
| D3 | action space | skill verbs + **two-tier** capability manifest (verb tier + Body Profile tier); 7+1 demoted to in-device VLA detail, not the L3 language |
| D4 | safety | **three-tier** Phylax: portable policy (mindloop) + symbolic BT net (bodylink) + per-body reflex (firmware) |
| D5 | workspace shape | 4 members (`tempomem / worldsense / mindloop / bodylink`); **bodylink = the adaptation framework, each robot = one out-of-tree device package** (G1-D first); product name Chronotope, root-repo rename optional |
| K1 | track-before-fuse | yes — SAM2/ByteTrack `track_id` into `Detection.aux`, arbiter uses it as prior |
| K2 | skill-card format v1 | flat steps + rules; DAG reserved via schema version |
| K3 | crystallization gate | always human-reviewed before a card enters the library |

**Multi-body is a first-class requirement, not a future nicety.** bodylink
ships the `ExecutorAdapter` protocol + Body Profile Registry + verb manifest +
reference BT runtime + MockBody; every body (G1-D wheeled 32-DOF first, then
legged / desktop-arm / future forms) is a separate out-of-tree package filling
it, differentiated only by Profile + verb set. The Sensor Stem zero-pad policy
keeps sensor-config differences from leaking past the seam.

## 10. Naming (per B2R convention: philosophy-first, engineering subtitle)

Candidates, owner to confirm: **Psyche** = Deliberation layer (carried over
from B2R), **Episteme** = skill-card library (from B2R's skill-web design),
**Phylax** = safety (carried over), **Hexis** (Aristotle, ἕξις "acquired
disposition") = Habit layer. Soma stays with the body/executor side.

## 11. Body-contract alignment — G1-D wheeled humanoid (ratified 2026-06-11)

The first body team (G1-D: wheeled base + dual 6-DOF arms + dexterous hands,
32 DOF, Jetson AGX Orin) delivered its L2/L1 design plus asks on L3. Their
L3↔L2 contract independently converges on this architecture: subtask
vocabulary ≈ skill verbs (D3); joint space stays strictly below L2; L1
hardware safety (dual-channel e-stop, safety PLC, STO/SS1/SLS) is exactly the
Reflex tier (D4); their error escalation (L2 self-heals IK/nav,
`ERR_GRASP_FAILED`/`ERR_OBJECT_LOST` rise to L3) is the replan loop; and
their "world model" slot (semantic map + object state tracking, 100–500 ms
query budget) is Chronotope. Their ROS 2 interface is adopted as
**ExecutorAdapter wire binding v0**.

Ruled by the owner, 2026-06-11:

| # | Rule |
|---|---|
| B1 | **The VLA fast path is out of brain scope.** The body-side "VLA module" (a rule-engine + template matcher, <10 ms — not a VLA policy model) dispatches *upstream* of the brain: VLA hit → straight to L2; miss → brain S2. The brain does not own or manage the VLA template library; Episteme stays the brain's own knowledge layer. The <100 ms fast-path requirement therefore does not bind the brain. |
| B2 | Latency contract accepted: simple task 0.5–2 s, complex 2–10 s, world-model query 100–500 ms (Chronotope is well under). |
| B3 | `error_code` + `recovery_actions` are standardized into the ExecutorAdapter contract: typed `ERR_*` enum + typed adjustment vocabulary (`position_offset`, `orientation_relax`, `force_adjustment`, …) — never free text. |
| B4 | Charging/battery tasks = a built-in Episteme card; no new mechanism. |
| B5 | The brain ships a health-check interface mirroring their L3 init checklist (`llm_model` / `world_model` / `task_library`). |
| B6 | Compute: S2 runs onboard **only on Thor**. Any non-Thor body (G1-D's Orin included) runs S2 in the cloud — `base_url` switch, protocol unchanged. |
| B7 | Redis: per this design, not theirs — the brain core stays transport-agnostic; the seam binding is native ROS 2 Service/Topic with no Redis dependency. |
| B8 | Frames: everything entering memory is **world frame** (right-handed, meters). Base-frame ↔ world-frame conversion is owned by L2. |
| B9 | Id space: subtasks dispatched by the brain carry memory **node ids**; L2 echoes them back verbatim in feedback. String aliases (`bottle_1`) do not cross the seam — the `cited_node_ids` audit chain stays closed. |
| B10 | Capability manifest: G1-D is the first manifest instance (verbs: `navigate` / `grasp` / `place` / `detect` / `open_door` / `charging` …; 2-D base, no legged locomotion). Body team to expose it — proposal: `/l2/capabilities` service (missing from their spec). |

Wire binding v0 (seam ↔ their names):

| ExecutorAdapter | G1-D ROS 2 |
|---|---|
| task entry (into brain) | `/l3/task_execute` (`TaskExecute.srv`) — served by the brain's ROS wrapper in the device package, not by brain core |
| `dispatch(subtask)` | `/l2/execute_subtask` (Service) |
| status stream | `/l2/task_status` (`TaskStatus.msg`: `task_id` / `subtask_id` / `status` / `progress` / `error_code` / `recovery_actions`) |
| capability manifest | `/l2/capabilities` (proposed, B10) |
| detections → memory | `/detection/objects` (`DetectionArray`, 5–15 Hz) → `add_detections()` |
