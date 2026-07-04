> 🌐 **English** · [中文](../zh/phylax-fmea.md)

# Phylax FMEA — failure-mode analysis → policy coverage (T5-10)

Closes the long-open "policy enumerated from B2R hard-constraints, not from a
failure-mode analysis" item. Method: enumerate how the household robot can hurt
someone or violate trust — per channel — and check each mode against an
existing guard. A mode with no guard becomes code (this pass produced the
`conservative_policy()` preset and confirmed one structural coverage).

## Failure modes × guards

| # | Failure mode | Guard | Status |
|---|---|---|---|
| 1 | Child commands a dangerous verb | `adult_only_verbs` (permission.adult_only) | covered |
| 2 | Child commands a dangerous *value* of a benign verb (stove, knife) | D1 `adult_only_verb_params` (permission.adult_only_param) | covered; `conservative_policy()` ships the preset |
| 3 | Guest/stranger routed into a private region | Q6 `guest_blocked_regions` + unknown-region refusal (region.*) | covered |
| 4 | Wrong service role acts in a restricted region | D-A `service_permitted_regions` (grant ∩ need, D-O) | covered |
| 5 | Fast motion near a human | `max_speed_mps_near_human` (0.2 in the conservative preset) | covered |
| 6 | Allergen served to unknown-status person | D-K menu invariant, fail-closed (allergy.*) | covered |
| 7 | Untrusted skill card loosens safety | `trusted_provenances` + learned cards carry no safety keys (D-L) | covered structurally |
| 8 | Barge-in / clarifier answer smuggles a blocked action | every replan path re-vets through the same gate | covered (tested) |
| 9 | Guest talks the robot into a role or a policy change | roles: no self-escalation (D-O); policy: `replace_policy` is adult-only and unreachable from barge/clarify paths | covered (T5-10) |
| 10 | Reliability score buys a safety pass | Phylax never reads `VerbSpec.reliability` (D-P guard) | covered (tested) |
| 11 | Offline degradation loosens the gate | P7.4 offline gate is swap-in tighten-only; `conservative_policy()` is the recommended fill | covered |
| 12 | Wet floor after mopping, person walks in | D-D `mop` expansion brackets with `warn_wet_floor` — structural, not policy | covered structurally |
| 13 | Repeated physical faults (COLLISION) keep retrying near people | Replanner caps (≤2/target, ≤6/task) then escalate-stop; retries carry `negation_constraints` | covered |
| 14 | Hot-liquid handling near a person | **gap** — needs body-side thermal/proximity signal (below L2 today) | deferred to the D3 real-HW track |
| 15 | Battery dies mid-carry over a fragile object | typed `BATTERY_LOW` escalates; graceful set-down is a body/BT concern | deferred (body tier) |

## Outcome

- New: `conservative_policy()` preset (modes 2/5/11) + `Phylax.replace_policy`
  adult-only override (mode 9) + `negation_constraints` on retries (mode 13).
- Open (hardware-gated): modes 14–15 need body-side signals — tracked with the
  D3 real-HW track, not as Phylax rules.
