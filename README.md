# spatialmem-brain

The **brain / LLM layer** for **[SpatialMem](https://github.com/wikieden/spatialmem)** —
binds memory + reasoning (+ optional perception) into one cognitive loop.

> **Why a separate repo?** SpatialMem core is the *memory* (hippocampus) and
> stays numpy-only with just the protocol seams. The concrete LLM integration
> and orchestration — the *brain* — lives here, like perception lives in
> `spatialmem-perception`. Core ships the `Verbalizer` protocol; this repo ships
> the model that fills it and the loop that drives it.

## What's here

| Piece | Role |
|---|---|
| `Brain` | cognitive loop: `observe`/`ingest` (perceive → remember) + `ask` (retrieve → reason) |
| `Reasoner` protocol, `VerbalizerReasoner`, `ScriptedReasoner` | turn a question + serialized scene → cited `Answer` |
| `CosmosReasonVerbalizer` | NVIDIA Cosmos Reason NIM as the `answer()` backend (stdlib-only) |
| `Answer` (`text` + `cited_node_ids`) | grounded reply citing memory node ids |

## Architecture

```
RGB(-D) ─► [spatialmem-perception adapter] ─► Detections
                                               │
                                               ▼
                                   spatialmem (memory: fuse/persist/query)
                                               │ serialize
                                               ▼
                       Brain.ask ─► Reasoner (LLM) ─► Answer(text, cited ids)
```

Full system design: [docs/cosmos3-spatialmem-llm-brain.md](docs/cosmos3-spatialmem-llm-brain.md).

## Install

```bash
pip install spatialmem-brain                 # memory + reasoning
pip install spatialmem-brain[perception]     # + spatialmem-perception (the eyes)
```

(`spatialmem` is the core dependency; `spatialmem-perception` is the optional
full-stack extra.)

## Quickstart (Topology B — BYO LLM)

```python
from spatialmem import SpatialMemory
from spatialmem_brain import Brain, VerbalizerReasoner, CosmosReasonVerbalizer

mem = SpatialMemory.open("home.smem", embedding_dim=512)
brain = Brain(mem, VerbalizerReasoner(CosmosReasonVerbalizer(model="nvidia/cosmos-reason2-8b")))
brain.ingest(detections)                 # remember (BYO perception)
print(brain.ask("where is the mug?"))    # retrieve -> reason -> cited Answer
```

Tests use `ScriptedReasoner` (deterministic, no network).

## License

Apache-2.0 — see [LICENSE](LICENSE).
