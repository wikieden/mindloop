> 🌐 **English** · [中文](../zh/access-control.md)

# Owner access control — runtime policy override (T5-10)

Closes the flagged "owner access-control spec" (TASK-FAMILIES §1.2): how region
policy and permissions change **at runtime**, and who may change them.

## Rules

1. **One door.** The only runtime override is `Phylax.replace_policy(new_policy,
   actor_role=...)` — a whole-`Policy` swap. There is no per-field mutation API;
   a policy is reviewed and replaced as a unit (same reasoning as D4 §9's
   "block the whole plan").
2. **Owner-class only.** `actor_role` must be `"adult"`; anything else raises
   `PermissionError` and the standing policy is untouched (refused loudly,
   logged). The four-role model (`adult/child/guest/stranger`) is unchanged —
   "owner" is an adult with physical/account access to the robot's console.
3. **No self-escalation (D-O).** No code path reaches `replace_policy` from a
   barge-in utterance, a Clarifier answer, or an LLM plan — the override is
   console/API territory, never conversational. A guest cannot talk the gate
   open; neither can the robot itself.
4. **Task-boundary only.** Callers apply an override between tasks (the gate is
   re-read per turn); an in-flight plan finishes under the policy it was vetted
   with.
5. **Offline never loosens.** The P7.4 `offline_policy` swap-in is tighten-only
   by convention; `conservative_policy()` is the recommended fill. An owner
   override while offline still requires the adult actor.

## What this is not

- Not identity/authentication — *who counts as an adult* is the device
  package's problem (voiceprint, app login, physical button). This spec starts
  where identity ends.
- Not per-utterance permission prompts — standing policy is data (`Policy`),
  authored per deployment, changed rarely and deliberately.
