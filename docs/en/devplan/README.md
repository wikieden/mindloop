> 🌐 **English** · [中文](../../zh/devplan/README.md)

# mindloop L3 Brain — Development Plan (index)

This directory holds the phased development plan for the L3 cognitive brain.
**L1/L2 execution is deferred** — its design reuses Brain2Robot; `bodylink`'s
`MockBody` is the only body used throughout L3 development.

| Doc | What |
|---|---|
| [DEV-PLAN.md](DEV-PLAN.md) | the complete phased plan (P0–P6), milestones, risks, sequencing |

## At a glance

```
P0 contracts ─► P1 intent+plan ─► P2 Episteme ─► P3 Phylax ─► P4 trace+replan ─► P5 full loop ─► P6 production
```

| Phase | Theme | Milestone |
|---|---|---|
| P0 | Seam contracts + test scaffolding | — (mostly done) |
| P1 | Intent routing + planning skeleton | M-L3.1 |
| P2 | Episteme skill-card library | M-L3.2 |
| P3 | Phylax policy tier | M-L3.2 |
| P4 | L4 Trace + replanning | M-L3.3 |
| P5 | Dialogue + full S2 loop | M-L3.3 |
| P6 | Production reasoner + eval + cloud bootstrap | M-L3.4 |

**Authority:** decisions D1–D5 + K1–K3 and body-contract B1–B10 in
[../brain-architecture.md](../brain-architecture.md). Each phase consults the
matching Brain2Robot design doc first. Spec each phase before coding.
