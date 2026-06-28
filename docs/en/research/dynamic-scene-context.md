> 🌐 **English** · [中文](../../zh/research/dynamic-scene-context.md)

# Dynamic scene context + semantic-map integration (design)

**Status:** design (2026-06-28). Defines the seam + the perceive-act-update loop;
**not yet implemented** (interface skeletons only — §6). Companion to
[l3-l2-fusion-roadmap.md](l3-l2-fusion-roadmap.md).

How the LLM gets the scene today (static, one-shot), how to make it dynamic
(re-query the live map during execution), and how the tempomem semantic map is the
hub that makes both work.

---

## 1. Status quo — static, one-shot per call

**Write path (map update, caller-driven).** `Brain.observe(rgb, depth, pose)`
(`brain.py:88`) → `mem.add_frame` (stage) → `mem.commit()` (the fuse-arbiter:
dedup / merge / update pose) → the `.smem` scene graph. Or `Brain.ingest(
detections)` (`brain.py:105`). The map is only updated when the caller feeds
frames.

**Read path (context injection, frozen per inference).** Inside `ask`
(`brain.py:110`) and `_plan_context` (`brain.py:296`):

```
mem.query(text, k)            # router: relational edges → semantic vec → keyword
   → top-k node_ids
mem.serialize(format="prompt", node_ids=…, max_tokens=budget)
   → subgraph string: the hits + their 1-hop relations + hierarchy ancestors,
     token-budgeted (falls back to the whole scene if nothing matched)
   → context  ──►  reasoner.reason(q, context) / planner.plan(instr, context)
```

**Why "static":** the context is serialized **once, at the start of `handle()`**.
A multi-step task is **planned once** from that snapshot; while the robot moves and
the world changes, the context is **not** refreshed and the plan is not
re-grounded. `brain.py` says so: *"Active perception (LLM → re-look) is future
work."* This design is that future work.

---

## 2. Dynamic design — the map is the single source of truth

The tempomem map is **already dynamic in storage** — `query` routing,
`serialize` subgraphs, and the maintenance mutators (`decay`, `forget`,
`consolidate`, `resplit`, `relate`, `define_region`, `update`). The gap is purely
the **inference-time re-injection loop**: re-query the live map at the right
moments. "Dynamic context" is not a new store — it is *when* you re-serialize.

### 2a. Three sources keep the map live

1. **Perceptual re-look (the eyes).** During execution — on a pose delta, a
   failure, or an explicit request — re-perceive: `observe` → fuse → `map v#++`.
2. **Effect write-back (symbolic, no camera).** On a `SubTask` SUCCESS, apply its
   `effects` (`robot.holding=apple`, `apple.location=trash`) to the map. Cheap,
   closes the loop without opening a camera. (Today `effects` are carried but not
   applied — D4; this wires the application.)
3. **Decay / forget (time).** Unseen objects decay; `consolidate` ages the map.
   Already present.

### 2b. Re-injection triggers (when to re-serialize for the LLM)

A fresh context is **not** built every step — only when the focus actually moved:

1. a **new instruction** (today's behavior);
2. a **dispatch failure** → P4 replan re-queries a fresh context;
3. an **effect write-back or new perception touched a node the plan depends on**
   (the *focus* set) → precondition recheck → re-vet / replan the plan tail;
4. the **reasoner asks to re-look** (active perception).

### 2c. The cycle

```
        ┌───────────────────────── tempomem semantic map (v#) ──────────────────────┐
        │  objects · relations(on/in/near) · regions · vectors · episodic(L4 trace)  │
        └───▲────────────▲───────────────▲──────────────────────────────┬───────────┘
            │            │               │                              │ query(focus)+serialize
   ③ decay  │   ② effects│ write-back    │ ① re-look (observe→fuse)      ▼  → context@v
   (time)   │   (SUCCESS)│               │                       ┌──────────────────┐
            │            │               │                       │ reasoner/planner │ LLM
            │            │               │                       └────────┬─────────┘
            │            │               │                                │ plan / answer
            │      ┌─────┴─────┐   ┌──────┴───────┐                        ▼
            │      │  apply    │   │ active       │                ┌──────────────┐
            │      │  effects  │   │ perception   │                │ dispatch     │
            │      └─────▲─────┘   └──────▲───────┘                │ subtask      │
            │            │ success        │ between steps          └──────┬───────┘
            │            │                │                               │ StatusUpdate
            │      ┌─────┴────────────────┴───────┐   fail (P4)           ▼
            └──────┤  StatusUpdate (typed + ids)   ├───► replan: re-query fresh context
                   └───────────────────────────────┘
   re-serve context only when v# AT THE FOCUS bumps (version-gated cache).
```

The closed loop: `map → context → LLM → plan → dispatch → status → {effects |
replan | re-look} → map`. Effect write-back means a multi-step task stays grounded
**without opening a camera every step** — re-look only when symbolic prediction is
uncertain.

---

## 3. Semantic-map application

| Dimension | tempomem has | dynamic use |
|---|---|---|
| **spatial-semantic retrieval** | `query` router (relational / vector / keyword) | focus = the subgraph relevant to the *next action*, not the whole map |
| **regions / zones** | `define_region` | context carries the robot's current region + the target region → navigation + P3 forbidden zones |
| **relations as grounding** | on / in / near edges | resolve "the one on the table"; edges get updated by effect write-back |
| **episodic / temporal** | L4 trace (P4) + decay | context can include "last seen" recency; the trace explains *why* a node's state is what it is |
| **affordances** (future) | nodes carry skill hints | the planner reads affordances to choose verbs |

---

## 4. Focus + version gating (the efficiency knob)

- **focus(turn)** = the query terms (instruction / question) ∪ the plan's target
  `node_ids` ∪ the robot's current region.
- **map version `v#`** bumps on every `commit` and every effect write-back.
- Context is cached by `(focus, v#)`; it is **re-serialized only when a `v#` change
  intersects the focus**. So a far-away object moving does not force a re-plan, but
  the cup you are about to grasp disappearing does.

---

## 5. Integration points (walkthrough, `brain.py`)

| Where | Today | Add |
|---|---|---|
| `ask` (`:110`), `_plan_context` (`:296`) | inline `query`+`serialize` | call a `SceneContextProvider` (factored seam) returning `(context, version)` |
| `observe`/`ingest` (`:88`/`:105`) | caller-driven map writes | also callable mid-execution by `ActivePerception` |
| `_dispatch_plan` (`:243`) | dispatch each subtask once | between subtasks: effect write-back on SUCCESS; staleness check vs focus; re-look policy |
| `_repair` (`:270`) | replan from the typed failure | replan **re-queries a fresh context** (not the stale plan-time one) |
| `handle` (`:163`) | one context at the top | the top context is `v0`; the loop re-serves on triggers |

---

## 6. Seam interface skeletons (not implemented — define first)

```python
# scene_context.py — factor the read path out of brain.py (behavior-identical first)
class SceneContextProvider(Protocol):
    def context(
        self, focus: Focus, *, max_tokens: int
    ) -> tuple[str, int]:                      # (serialized subgraph, map version)
        ...

@dataclass(frozen=True)
class Focus:
    query: str                                 # instruction / question
    node_ids: tuple[int, ...] = ()             # plan targets to keep in view
    region: str | None = None                  # robot's current region

# effect_apply.py — close the symbolic loop (D4 carried → applied)
class EffectApplier(Protocol):
    def apply(self, effects: tuple[str, ...]) -> int:   # returns new map v#
        ...

# active_perception.py — when to re-look during execution
class ActivePerception(Protocol):
    def should_relook(
        self, *, last_status: StatusUpdate, focus: Focus, map_version: int
    ) -> bool:
        ...
```

A first cut is **behavior-preserving**: `DefaultSceneContextProvider` wraps exactly
today's `query`+`serialize`; `EffectApplier`/`ActivePerception` default to no-ops.
Then turn each on behind a flag.

---

## 7. Phasing

1. **Factor** `SceneContextProvider` out of `ask`/`_plan_context` — no behavior
   change, just a seam + a `version`.
2. **Effect write-back** — apply confirmed `effects` to the map on SUCCESS; re-vet
   the plan tail's preconditions against the updated map.
3. **Version-gated re-serialize** — re-query fresh context on replan + on a
   focus-touching `v#` bump.
4. **Active perception** — an `observe` hook between steps / on uncertainty; the
   reasoner may request a re-look.

Each step is independently shippable and network-free testable (scripted
perception + a mock map version).
