# Changelog

All notable changes to mindloop (the L3 brain for Chronotope) are documented
here. Format follows [Keep a Changelog](https://keepachangelog.com/); versions
follow SemVer (pre-1.0, the API may change between minor releases).

## [Unreleased]

### Added

- **Executor seam (P0, D1/D3)** — `execute.py`: the `ExecutorAdapter` protocol
  the brain dispatches against, plus its value types. `SubTask` carries
  open-vocabulary skill verbs + tempomem scene-graph node ids (B9), never joint
  space (D3/B8). `StatusUpdate` reports back with typed `ErrorCode` +
  `RecoveryHint` (B3) and echoes the node ids. `CapabilityManifest` is two-tier
  (D3): a `VerbSpec` verb tier the planner reads + a `BodyProfile` tier the
  executor uses. `dispatch()` streams `StatusUpdate`s (mirrors `/l2/task_status`).
- **`PreferenceStore` protocol stub (L5, D2)** — `preference.py`, provisional.
- **`Brain.health()` + `HealthReport` (B5)** — `health.py`: brain readiness
  mirroring the body team's L3 init checklist.
