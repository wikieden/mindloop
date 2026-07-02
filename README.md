> 🌐 **English** · [中文](README.zh.md)

# mindloop

The **brain / LLM layer** for **[Chronotope](https://github.com/wikieden/tempomem)** —
binds memory + reasoning (+ optional perception) into one cognitive loop.

> **Why a separate repo?** Chronotope core is the *memory* (hippocampus) and
> stays numpy-only with just the protocol seams. The concrete LLM integration
> and orchestration — the *brain* — lives here, like perception lives in
> `worldsense`. Core ships the `Verbalizer` protocol; this repo ships
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
RGB(-D) ─► [worldsense adapter] ─► Detections
                                               │
                                               ▼
                                   tempomem (memory: fuse/persist/query)
                                               │ serialize
                                               ▼
                       Brain.ask ─► Reasoner (LLM) ─► Answer(text, cited ids)
```

Full system design: [docs/cosmos3-tempomem-llm-brain.md](docs/en/cosmos3-tempomem-llm-brain.md).
Production three-layer brain (Deliberation / Habit / Reflex) — proposal &
decision record: [docs/brain-architecture.md](docs/en/brain-architecture.md).

## Install

```bash
pip install mindloop                 # memory + reasoning
pip install mindloop[perception]     # + worldsense (the eyes)
```

(`tempomem` is the core dependency; `worldsense` is the optional
full-stack extra.)

## Quickstart (Topology B — BYO LLM)

```python
from tempomem import TempoMem
from mindloop import Brain, VerbalizerReasoner, CosmosReasonVerbalizer

mem = TempoMem.open("home.smem", embedding_dim=512)
brain = Brain(mem, VerbalizerReasoner(CosmosReasonVerbalizer(model="nvidia/cosmos-reason2-8b")))
brain.ingest(detections)                 # remember (BYO perception)
print(brain.ask("where is the mug?"))    # retrieve -> reason -> cited Answer
```

Tests use `ScriptedReasoner` (deterministic, no network).

## Self-host the reasoner

Point `CosmosReasonVerbalizer(base_url=...)` at a local OpenAI-compatible server
(vLLM or an NVIDIA NIM container) — e.g. Cosmos-Reason2-8B on an RTX PRO 6000
(96 GB). Step-by-step (variants, VRAM, serve commands, wiring):
**[docs/local-serving.md](docs/en/local-serving.md)**. Runnable skeleton:
`examples/02_local_reasoner.py`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
