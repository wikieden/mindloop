> 🌐 **English** · [中文](../../../zh/devplan/specs/P5-dialogue-full-loop.md)

# P5 spec — Dialogue + full S2 loop (M-L3.3)

**Status:** implemented (2026-06-28). Implements [DEV-PLAN.md](../DEV-PLAN.md) §P5,
closing **M-L3.3** (P4 + P5). **B2R reference:** `05_scenarios/e2e_walkthrough.md`,
`breakfast_e2e.md` (multi-task: task + question + social, per-person identity
context, multi-step, replan).

## 1. What's net-new

The single-instruction loop already runs end-to-end through P4:
`route → plan → compile (D3) → policy (P3) → dispatch → bounded replan (P4) → trace`.
P5 adds the two things that turn it from one-shot into a **conversation**, then
proves the whole thing on a reproduced household scenario:

1. **Multi-turn dialogue** — a `Conversation` carries turn history, so a question
   or chat turn is answered with the recent turns as context ("the other one" →
   resolves against the prior turn). Memory-grounded (extends `ask`).
2. **L5 preference overlay** — per-person preferences (`PreferenceStore`) override
   skill-card param defaults, filtered to the verbs the body declares.
3. **E2E scenario test** — one multi-turn conversation exercising question → task
   (success) → task (replan→recover) → task (safety-blocked), fully cited + traced,
   no real network. This is the M-L3.3 integration proof.

## 2. Multi-turn dialogue (`dialogue.py`)

- **`Turn`** = `(instruction, HandleResult)`. **`Conversation`** = an ordered list
  of turns + `history_text(n)` rendering the recent `n` turns for context.
- **`Brain.converse(instruction, conversation=None, *, person="", safety_context=None)
  -> HandleResult`** — runs `handle` with the conversation's recent history threaded
  into `ask` (question/chat turns become memory-grounded *and* dialogue-grounded),
  then appends the turn. Single-turn `handle` is unchanged (dialogue is opt-in).
- Task turns don't need dialogue context to plan (the instruction is self-contained
  in the MVP); the history feeds **answering**, where follow-ups arise.

## 3. Preference overlay (L5, D2)

- `PreferenceStore` gains **`all(person) -> Mapping[str, str]`** (a person's full
  preference map) alongside `get`. A concrete in-memory **`DictPreferenceStore`**
  ships for tests/deployments; a real backend (e.g. Mem0) stays external (D2 —
  preferences are out of the memory core for lifecycle/privacy).
- `Brain(preferences=…)` + `handle(..., person=…)`: after a task plan is compiled,
  the brain **overlays the person's preferences onto each SubTask's params**,
  filtered to the param keys the body declares for that verb (`manifest`-gated, so a
  preference can't inject an unknown param). Preferences win over card/rule defaults
  — the user's stated choice tops a generic default. Done in the brain post-compile
  (no `Planner`-protocol change), so it applies to LLM and skill-card plans alike.

## 4. The full loop, as one conversation

```
person + instruction (turn N)
   │  Conversation history ──┐
   ▼                         ▼
Brain.converse → handle:
   route ─ question/chat ─► ask(+ dialogue history) ─► cited Answer
        └ task ─► plan ─► compile (D3) ─► preference overlay (L5)
                        ─► Phylax (P3) ─► dispatch ─► bounded replan (P4)
                        every step ─► TraceStore (B9 node ids)
   ► HandleResult ─► appended to the Conversation
```

Nothing in the loop changed; P5 wraps it with conversation state + the preference
overlay, and demonstrates it on a scenario.

## 5. Files

`dialogue.py` (new: `Turn`, `Conversation`) · `preference.py` (`all` + concrete
`DictPreferenceStore`) · `brain.py` (`converse`, `person=`, `preferences=`,
preference overlay) · `__init__.py` · `tests/test_dialogue.py` (new, incl. the e2e
scenario).

**Tests / Exit (M-L3.3):** a multi-turn conversation runs question → task(success)
→ task(replan→recover) → task(safety-blocked) end-to-end against MockBody /
`_FlakyBody`, every answer citing node ids and every dispatch in the trace; a
follow-up question resolves against prior-turn context; a person's preference
overrides a card default (manifest-gated). The full S2 loop is reproduced with no
real network. ✅
