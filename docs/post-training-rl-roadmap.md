# Post-training & RL roadmap — which models to train, and how

**Status:** design / forward-looking. Companion to
[cosmos3-spatialmem-llm-brain.md](cosmos3-spatialmem-llm-brain.md) (the embodied
brain architecture).
**Audience:** anyone deciding where to spend training budget across the
three-faculty brain (perception VLM · spatial memory · reasoning LLM).
**Scope:** what to post-train (SFT), what to reinforce (RL), what to leave
frozen, and the data flywheel that pays for it.

> One-line thesis: **spend the RL budget on the reasoning cortex, not on
> perception or the encoder.** The cortex is the only component whose objective
> is a multi-step decision with an *automatically verifiable* reward, which is
> exactly where RL beats supervised learning. Everything else is either dense
> supervision (perception) or not a learned model at all (memory fusion).

---

## TL;DR — the decision matrix

| Component | Where it lives | Post-train? | Method | Priority |
|---|---|---|---|---|
| **Reasoning cortex** (`Reasoner` / `Brain.ask`) | `spatialmem-brain` | ✅ highest value | SFT cold-start → **RL (RLVR)** | **P1** |
| **Cosmos perception VLM** | `spatialmem-perception` | ✅ but SFT only | supervised / distillation (format + grounding) | P2 |
| **C4 active-perception policy** ("look closer at node N") | `spatialmem-brain` | ⚠️ optional | rule-based v0 → **policy RL** later | P3 |
| **CLIP/SigLIP crop encoder** | `spatialmem-perception` | ❌ avoid | frozen — see §6 | — |
| **SpatialMem fusion/arbiter** | `spatialmem` (core) | ❌ no model | threshold *tuning* (search), not training | — |

---

## 1. The reasoning cortex — the one RL is built for (P1)

The cortex is the `Reasoner` (`reason(question, context) -> Answer`) that `Brain`
drives: it reads the serialized scene (C2), calls memory tools (C3), and answers
citing `node_id`s. This is a **multi-step decision process with a checkable
outcome** — the textbook case for RL with verifiable rewards (RLVR).

### Why RL fits here and nowhere else

Three properties the cortex has that perception/encoders do not:

1. **The reward is automatically verifiable.** Did the answer match? Do the
   cited `node_id`s actually exist in the store? Were they the *right* ones?
   All checkable in code, no human labels per episode.
2. **The objective is sequential.** Tool-call order, when to stop, when to
   request a re-look — these are policy decisions, not a single labelled target.
3. **Credit assignment matters.** A good final answer reached via a wrong tool
   path should not be reinforced the same as a clean path.

### Reward design (RLVR)

```
reward =  w1 · task_success        # answer correct vs. ground truth (eval harness judges)
        + w2 · citation_grounded   # every cited node_id exists in the store (tools verify)
        + w3 · citation_relevant   # cited nodes are the ones that actually answer it
        - w4 · steps               # fewer tool calls / reasoning steps is better
        - w5 · hallucination       # cited a node_id that does not exist  → hard penalty
        - w6 · injection_breach    # obeyed an instruction embedded in untrusted SCENE text
```

Notes:
- `w5` (hallucinated id) and `w6` (prompt-injection breach, see brain design §10)
  should be large, asymmetric penalties — these are the failure modes that make
  an embodied agent untrustworthy.
- `citation_grounded`/`citation_relevant` are cheap: the C3 tool layer already
  returns `node_id`s, so a verifier just checks set membership and overlap with
  the gold support set.

### Two-stage training

1. **SFT cold-start (do this first).** Pure RL from a base model on a tool-using
   task is slow and unstable. Collect successful trajectories — `(question,
   serialized scene, tool calls, tool results, final answer with citations)` —
   and SFT on them. Goal: instil the *habit* "serialize → semantic/spatial query
   → cite `node_id` → answer", and the refusal habit "if memory lacks it, say
   so." `ScriptedReasoner` is the offline harness for generating/replaying these
   traces deterministically.
2. **RL (GRPO or PPO) on the reward above.** Once the policy reliably emits
   well-formed tool calls, switch to RL to optimise success/steps/grounding.
   GRPO is attractive here: no separate value model, group-relative advantage,
   works well when the reward is a verifiable scalar.

### Where the training data comes from

The brain design §16 "memory-advantage eval" — *questions answerable only with
cross-clip/cross-session persistence* (object seen in clip 1, asked in clip 9) —
**is the RL environment.** Each episode:

- replay a clip stream into a fresh `SpatialMemory` store,
- pose a question whose answer requires the persisted memory,
- let the cortex act through the tools,
- score with the reward function above.

SpatialMem is the world-state/memory backend of the RL loop; the eval harness is
the reward source. No new simulator needed to start.

---

## 2. Cosmos perception VLM — SFT only, do not RL (P2)

Perception (the `Cosmos3PerceptionAdapter` in `spatialmem-perception`) turns RGB
into structured 3D boxes. Two reasons to keep it on **supervised** learning:

- **Dense ground truth exists.** 3D boxes / labels are directly labellable (or
  distillable from a stronger teacher). Supervised learning is far more
  sample-efficient than RL when you have per-output targets.
- **The objective is single-step.** "Given this frame, emit these boxes" has no
  sequential credit-assignment problem that RL would help with.

What to actually do:

- **Format-alignment SFT:** make the model emit the exact JSON contract the
  adapter expects (`{label, center, size, orientation}` + ego-pose estimate),
  stably, every time. Most of the practical win is here.
- **Grounding SFT / distillation:** improve open-vocab recall on your object
  classes by distilling from a larger detector or fine-tuning on domain frames.

The *only* perception-side decision that is RL-shaped — "which way to look / what
to inspect" — is **not** the perception model; it is the C4 policy (§3).

---

## 3. C4 active-perception policy — RL later, rules now (P3)

C4 is the bounded "look closer at node N" loop (brain design §C4). The *decision*
of whether/where to re-look is a genuine policy and a fair RL target:

```
reward = info_gain(confidence_after − confidence_before)  −  action_cost(move + compute)
```

But for v0, keep it **rule-based**: a budget controller (max re-looks per tick /
per node, cooldown, cycle-breaker) is predictable, debuggable, and good enough.
Only swap the controller for a learned policy once you have logged enough
re-look trajectories to train on. RL here is an optimisation, not a prerequisite.

---

## 4. CLIP/SigLIP crop encoder — freeze it (do not train)

The crop encoder produces the feature vectors SpatialMem stores. **Do not
fine-tune it in place.** SpatialMem locks `embedding_dim` at store-create time
and assumes one encoder forever (brain design §9 / store compatibility):
re-training the encoder changes the embedding space, which invalidates every
vector already persisted. The only correct way to "change the encoder" is to
**re-embed into a fresh store** — a migration, not a training step. Treat the
encoder as a fixed, load-bearing dependency.

---

## 5. SpatialMem fusion/arbiter — tuning, not training

The memory layer (fusion, the merge arbiter, decay, split) is **pure algorithm,
no neural model.** Its `FusionConfig` thresholds (`tau_merge`, `tau_ambig`,
`w_geom/w_iou/w_sem/w_label`, decay half-life, …) are **hyperparameters**, tuned
by grid / Bayesian search against `bench.recall_at_k`, not learned by gradient
descent. Keep this distinction explicit so "improve memory" never gets
misfiled as a model-training task.

---

## 6. The data flywheel

```
deploy / eval  ──►  log trajectories (question, scene, tool calls, answer, outcome)
      ▲                                   │
      │                                   ▼
   better cortex  ◄── RL (RLVR) ◄── SFT cold-start ◄── filter to successful traces
```

- Every `Brain.ask` run is a candidate trajectory. Log `(question, serialized
  scene, ordered tool calls + results, final Answer + cited ids, verifier
  outcome)`.
- Filter to successes → SFT set. Use the full distribution (incl. failures) →
  RL signal.
- The memory-advantage eval keeps the reward honest: it specifically rewards
  *using persistent memory*, which is the whole reason the architecture exists.

---

## 7. Phasing

| Phase | Work | Output |
|---|---|---|
| T0 | Stand up the eval-as-environment (replay clips → store → question → reward) | RL/SFT harness |
| T1 | Collect + filter cortex trajectories; **SFT cold-start** the `Reasoner` | tool-using base policy |
| T2 | **RL (GRPO/RLVR)** on the cortex reward | grounded, fewer-step cortex |
| T3 | Perception **format/grounding SFT** in `spatialmem-perception` | stable 3D-box JSON |
| T4 | Log C4 re-look trajectories; train the **active-perception policy** | learned look controller |

Budget rule of thumb: **most of the RL spend on T1–T2 (cortex).** T3 is
supervised. T4 is optional and last.

---

## 8. Non-goals / cautions

- **No RL on perception** — dense supervision dominates; RL would be wasteful.
- **No in-place encoder fine-tune** — breaks store compatibility (§4).
- **No gradient training of the fusion layer** — it has no model (§5).
- **Reward hacking watch:** an agent can game `citation_grounded` by citing
  many ids, or game `steps` by answering blindly. Keep `task_success` dominant
  and penalise over-citation; audit with the held-out memory-advantage set.
- **Safety in the loop:** `injection_breach` must stay a first-class, heavily
  penalised reward term — untrusted scene text is an exfil vector (brain
  design §10), and RL will find the breach if it is not priced in.
