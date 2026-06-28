> 🌐 **English** · [中文](../../../zh/devplan/specs/P4-trace-replanning.md)

# P4 spec — L4 trace + failure-driven replanning (M-L3.3)

**Status:** implemented (2026-06-28). Implements [DEV-PLAN.md](../DEV-PLAN.md) §P4.
**B2R reference:** `l3/replanner.py`, `memory/trace_memory.py`, `trace_memory.md`,
the negation-driven-replanning loop in `L3_cognition.md`.

## 1. Idea — learn from failure, bounded

When a dispatched `SubTask` comes back `FAILED` with a typed `ErrorCode` +
`RecoveryHint` (B3), the brain repairs rather than giving up blindly — but the
repair is **bounded and monotonic**: a few adjusted retries, then it stops and asks
the user. Every attempt is logged to an append-only **L4 trace** (the negation-
learning fuel). Two new pieces, both stdlib + network-free:

```
dispatch SubTask ─► StatusUpdate
   │ SUCCESS ─► next subtask
   │ FAILED (typed ErrorCode + RecoveryHint, B3)
   ▼
Replanner.replan(failed, status) ─► bounded corrective SubTask[]
   • RETRY  → re-issue unchanged
   • ADJUST → re-issue + typed adjustment param (offset/relax/force)
   • REROUTE→ navigate to the object, then re-issue
   • SKIP   → drop the step, continue
   • ESCALATE (cap hit / no hint) → stop + speak, hand to the user
   ▼ corrective re-vetted by Phylax (P3 still applies), then dispatched
   ▼ every attempt + failure ─► TraceStore (append-only, cites node ids B9)
```

## 2. `TraceStore` (`trace.py`) — the L4 episodic memory

Stdlib sqlite, like tempomem's `.smem`. One append-only `episodes` table; an
attempt/failure is **never deleted** (a trace can't be erased — "clearing" a task
rotates the `session_id`). Every row cites tempomem **node ids** (B9), so the trace
is queryable by object (`by_node(id)`) and by session; `failures()` is the
negation-learning view. `log_attempt`/`log_failure`; `:memory:` for tests.

> **Scope (D2):** the dev plan envisions this merging into the tempomem core for
> one shared store. For P4 it lives in `mindloop` and cites node ids, which already
> satisfies the shared-id-space requirement; the core merge is a deferred,
> coordinated cross-repo change.

## 3. `Replanner` (`replan.py`) — typed failure → bounded correction

Pure function of the typed failure + per-instance counters (deterministic, no
network, no LLM — an LLM fallback is a future hook). It works at the **SubTask
level** (post-compile), reusing the failed step's node ids (B9) and adjusting
params, so no name round-trip is needed.

- **Caps (B2R):** per `(verb, node-ids)` target ≤ `max_per_target` (default 2); a
  global `max_total` (default 6) guards cross-step loops. Past either ⇒ **escalate**.
- **Hint mapping (B3 `RecoveryKind`):** `RETRY`→re-issue; `POSITION_OFFSET` /
  `ORIENTATION_RELAX` / `FORCE_ADJUSTMENT`→ADJUST (param `recovery`=kind); `REPLAN`
  →REROUTE (navigate + re-issue); `SKIP`→skip. No hint ⇒ escalate.
- **Escalation speak** draws from the skill card's `failure_hints` when given, else
  a default. `reset()` starts a new task (counters clear; the trace is untouched).

## 4. Brain integration (`brain.py`)

`Brain(replanner=…, trace=…)` (both opt-in). The dispatch step becomes a bounded
**replan loop** (`_dispatch_plan` / `_repair`): on a `FAILED` terminal it consults
the replanner, dispatches the corrective subtasks in place, and repeats until
success, skip, or escalation. **Safety still applies** — a corrective plan is
re-vetted by Phylax (P3) before it dispatches. An **escalation stops the whole
plan** and replaces `plan.speak` with the repair message; nothing loops forever.
Without a replanner, dispatch is exactly the P1-P3 single-shot behavior.

## 5. Files

`trace.py` (new) · `replan.py` (new) · `brain.py` (replan loop in `handle`) ·
`__init__.py` · `tests/test_replan.py` (new).

**Tests / Exit (M-L3.3, P4 half):** a flaky grasp → replan-adjust → succeeds, both
attempts in the trace (queryable by node id); a permanent failure → bounded retries
→ escalate (stop + speak, no infinite loop); typed-hint mapping (offset/replan/
retry/skip); per-target + global caps; no-replanner preserves P1-P3. ✅
