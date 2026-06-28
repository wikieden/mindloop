> 🌐 **English** · [中文](../../../zh/devplan/specs/P2-episteme-skill-cards.md)

# P2 spec — Episteme skill-card library (M-L3.2)

**Status:** implemented (2026-06-28). Implements [DEV-PLAN.md](../DEV-PLAN.md) §P2.
**B2R reference:** `techne_crystallization.md`, `household_task_taxonomy.md`,
`appliance_interaction.md` (procedural knowledge as data; appliance affordances).

## 1. Idea — procedural knowledge as data

A `SkillCard` is **how-to knowledge** ("do the laundry", "cook pasta") stored
declaratively, not as code. The card holds **flat steps + rules** (K2 — a DAG is
reserved via `schema_version`, not built yet). Turning a card into a dispatchable
plan is `instantiate()`; the card itself is inert data, authored in YAML or built
from a dict.

The output of `instantiate()` is a `Command` tuple — **the same intermediate
representation the LLM planner emits** (`plan.Command`). So a skill card and the
LLM are two *interchangeable sources* of the same verb sequence, and both flow
through the one downstream compiler (`compile_commands`: node-id binding B9,
SubTask metadata, manifest gate). No second execution path.

```
instruction
     │
     ▼
SkillCardPlanner.plan()                     ◀── a plan.Planner
     │  retrieve best card (semantic BYO-encoder | keyword)
     │  hit?  ── no ──►  inner LLM Planner  (fallback, flagged low-confidence)
     │  yes
     ▼
extract_slots(instruction, card)            "wash the wool sweater" → {fabric: wool}
     ▼
instantiate(card, manifest, slots, prefs)
     │  • fire Rules whose `when` slots match   (wool → program=delicate)
     │  • overlay rule params, then L5 prefs    (prefs win; only declared keys)
     │  • resolve each step's object slot
     │  • drop verb ∉ manifest                  (D3)
     ▼
tuple[Command]  ──►  compile_commands  ──►  SubTask[]  ──►  executor
```

## 2. Schema

`SkillCard`: `id`, `category`, `preconditions`, `rules`, `steps`,
`failure_hints`, `safety`, `provenance`, `schema_version`.

- **`SkillStep`** = `verb` + `target` (object slot or literal; `"{category}"`
  binds to the card category; empty ⇒ no object, e.g. `detect`) + `params`
  (step-level defaults).
- **`Rule`** = `when` (slot==value conditions, all must hold) + `set_params`
  (overlay) + `target_verb` (which step verb to overlay; empty ⇒ all). A rule
  *fires* when its `when` is satisfied by the situation slots.
- **`safety`** holds policy annotations the **Phylax tier (P3)** gates on. A card
  carrying `safety` from an untrusted source must be signed/reviewed before it is
  honored (P3) — `provenance` records origin.

## 3. Param precedence (lowest → highest)

1. per-verb table defaults (`compile_commands._VERB_TABLE`)
2. step `params`
3. firing `Rule.set_params`
4. L5 `preferences` (only keys the body declares for that verb)

The user's stated preference tops a generic rule; both top the card defaults.

## 4. Retrieval — BYO encoder

`SkillLibrary.retrieve(instruction, encoder=None, k=1)`: with an `Encoder`,
semantic cosine over `category + id + step verbs`; without, keyword overlap. No
hit ⇒ empty ⇒ the planner falls back to the LLM. Same BYO pattern as
`tempomem.query` — the heavy semantic backend is optional, keyword is the floor.

## 5. Fallback is flagged, never silent

`SkillCardPlanner` with no matching card defers to its inner LLM `Planner` and
**logs that the plan is low-confidence** (P2 contract: a no-card plan is flagged,
not passed off as curated knowledge). With no fallback wired, it returns `()`.

## 6. Dependencies

Core is **stdlib + the existing numpy**; cards build from dicts
(`SkillCard.from_dict`), so tests are dependency- and network-free. The YAML
loader `load_cards()` lazy-imports PyYAML behind the **`skills`** extra — the only
place a third-party dep appears.

## 7. Body change (bodylink)

`g1d_manifest()` gains an **`operate_appliance`** verb (`appliance_types`:
washer/stove/microwave/dishwasher) so laundry/cooking cards can drive appliances.
`MockBody.dispatch()` is verb-agnostic — no executor change.

## 8. Files

`episteme.py` (new) · `plan.py` (`Command.params` + merge) · `__init__.py`
(exports) · `cards/laundry_basic.yaml` + `cards/cook_pasta.yaml` (new) ·
`pyproject.toml` (`skills` extra) · `tests/test_episteme.py` (new) ·
`bodylink/src/bodylink/mock.py` (+verb) · CHANGELOGs.

**Exit (M-L3.2, P2 half):** laundry + cooking cards run end-to-end against
MockBody; wool/dark rules resolve to the correct program; a missing card falls
back flagged. ✅
