> 🌐 **English** · [中文](../../../zh/devplan/specs/P3-phylax-policy.md)

# P3 spec — Phylax policy tier (M-L3.2)

**Status:** implemented (2026-06-28). Implements [DEV-PLAN.md](../DEV-PLAN.md) §P3.
**B2R reference:** `design_doc/02_systems/safety_architecture.md` — §2 (L3 semantic
hard-constraints), §8 (permissions / proximity / stranger mode), §9 (Phylax
arbitration: signal priority + "upper want-to never overrides lower must-not").

## 1. Scope — the brain-side semantic tier only

D4's Phylax is three tiers: **semantic** (here, in the brain), symbolic-BT (in
`bodylink`), reflex (in firmware). P3 builds the **semantic tier only** — a
portable, declarative policy gate. The other two tiers are deferred.

## 2. Where it sits — a gate between plan and dispatch

```
route → plan → compile_commands → Plan ──► [ Phylax.check(plan, context) ] ──► dispatch
                                              │ violations?
                                              ▼ yes
                                   BLOCK whole plan: stop + speak,
                                   no reroute, no retry  (D4 §9)
```

`Brain.handle(..., safety_context=)` runs the gate **after** the manifest-gated
compile (D3) and **before** dispatch. A violation blocks the **entire** plan —
nothing is dispatched (`statuses == ()`), `HandleResult.violations` carries the
reasons, `HandleResult.blocked` is true, and `plan.speak` is replaced with a
refusal. The gate is **opt-in**: no `policy` wired ⇒ dispatch as in P1/P2.

## 3. The governing principle (B2R §9)

**Monotonic tightening: an upper layer's "want-to" never overrides a lower
layer's "must-not".** The gate only ever *subtracts* — it blocks, it never
reroutes or retries around a safety constraint. A safety-class block is terminal
(stop + speak), distinct from a task-class failure (which P4 may replan).

## 4. Declarative `Policy` + `SafetyContext`

`Policy` (data, authored per deployment):

| field | enforces (B2R) |
|---|---|
| `adult_only_verbs` | §8 — blade / power-tool verbs need `role="adult"` |
| `supervised_only_verbs` | §2 — fire / high-temp need a supervising adult |
| `forbidden_node_ids` | forbidden zones — a subtask targeting one is refused |
| `max_speed_mps_near_human` (+ `speed_param`) | §2/§8 — within 1 m of a person, a locomotion verb above the cap is refused |
| `trusted_provenances` | untrusted skill-card gate (§ below) |

`SafetyContext` (from the identity / perception layer, **conservative defaults**,
B2R §8 "unknown → conservative"): `role` (`adult`/`child`/`guest`/`stranger`,
default `stranger`), `humans_within_1m` (default `False`), `supervised`
(default `False`).

`Phylax.check(plan, context) -> tuple[Violation, ...]` returns every violation
(empty ⇒ cleared). Each `Violation` carries a `rule`, a `Severity`, a machine
`message`, the `subtask_id`, and a user-facing `speak`. The caller blocks on any.

## 5. Untrusted skill cards (§ community-card gate)

A `SkillCard` may carry `safety:` annotations and a `provenance` (P2). A card
with `safety:` from a `provenance` **not** in `trusted_provenances` (default just
`{"builtin"}`) is **refused before it is honored** — the signature/review gate.
`SkillCardPlanner(policy=phylax)` calls `Phylax.vet_card` and skips a refused card
(falling back to the LLM, or empty). A card with no `safety:` is always allowed.

## 6. Files

`phylax.py` (new: `Policy`, `SafetyContext`, `Violation`, `Severity`, `Role`,
`Phylax`, `refusal_speak`) · `brain.py` (`policy=` + the gate in `handle`) ·
`plan.py` (`HandleResult.violations` + `.blocked`) · `episteme.py`
(`SkillCardPlanner(policy=)` vets cards) · `__init__.py` · `tests/test_phylax.py`.

**Tests / Exit (M-L3.2, P3 half):** blade op by a non-adult → refused; over-speed
near a human → refused; forbidden-zone target → refused; unsigned `safety:` card →
refused; a clean plan clears and dispatches; **every dispatched plan has passed
the gate**, blocks carry traced `violations`. ✅
