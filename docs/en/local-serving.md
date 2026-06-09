> 🌐 **English** · [中文](../zh/local-serving.md)

# Local reasoner deployment (self-hosted Cosmos Reason)

Run the reasoner on your own GPU instead of the hosted NVIDIA gateway. The
`CosmosReasonVerbalizer` talks to any **OpenAI-compatible** `/v1/chat/completions`
endpoint, so you just stand up a local server and point `base_url` at it — no
code change.

Verified against NVIDIA primary sources (Cosmos-Reason2 GitHub, HF cards, NIM
docs) for a single **RTX PRO 6000 Blackwell (96 GB)** workstation.

## Pick a variant (BF16; weights ≈ params × 2 bytes)

| Model | Weights | Fit on 96 GB | When |
|---|---|---|---|
| **`nvidia/Cosmos-Reason2-8B`** | ~17 GB | ~75 GB free, full 256K ctx | **default** — standard reasoner, fast |
| `nvidia/Cosmos-Reason2-32B` | ~67 GB | ~25–29 GB free → 16–64k ctx; FP8 for 256k | highest reasoning quality |
| `nvidia/Cosmos-Reason2-2B` | ~5 GB | trivial | edge / many concurrent |
| `nvidia/Cosmos3-Nano` (16B) | ~32 GB | NVIDIA's RTX-PRO-6000 pick | omnimodel (reasoner+generator); heavier than a pure text reasoner |

For a text-out reasoner behind `answer()`, **Cosmos-Reason2-8B** is the pragmatic
choice. Cosmos 3 Nano is the full two-tower world model — use it only if you also
want world/action generation.

## Path 1 — vLLM (self-hosted, recommended)

```bash
pip install "vllm>=0.11.0" "transformers>=4.57.0"   # Cosmos-Reason2 ships in transformers; no --trust-remote-code needed
vllm serve nvidia/Cosmos-Reason2-8B \
  --max-model-len 16384 \
  --reasoning-parser qwen3 \
  --media-io-kwargs '{"video": {"num_frames": -1}}' \
  --gpu-memory-utilization 0.90 \
  --port 8000
# verify:  curl http://localhost:8000/v1/models
```

OpenAI-compatible server on `:8000` (`/v1/chat/completions`). 32B for 256k
context: add `--quantization fp8` (native on Blackwell) to drop weights to
~33 GB. (Cosmos 3 Nano is **BF16-only** — FP8/FP4/FP16 not officially supported.)

## Path 2 — NVIDIA NIM (turnkey container)

```bash
docker login nvcr.io        # username: $oauthtoken   password: <NGC_API_KEY>
export NGC_API_KEY=<your_ngc_key>
mkdir -p ~/.cache/nim
docker run --rm --runtime=nvidia --gpus all --shm-size=32GB \
  -e NGC_API_KEY -v ~/.cache/nim:/opt/nim/.cache -u "$(id -u)" \
  -p 8000:8000 nvcr.io/nim/nvidia/cosmos-reason2-8b:1.6.0
# request model id: "nvidia/cosmos-reason2-8b"; endpoint /v1/chat/completions
```

Check the NGC catalog (`catalog.ngc.nvidia.com/.../cosmos-reason2-8b`) for a tag
newer than `1.6.0` before deploying.

## Wire it (one line — `base_url`)

```python
from spatialmem import SpatialMemory
from spatialmem_brain import Brain, VerbalizerReasoner, CosmosReasonVerbalizer

vb = CosmosReasonVerbalizer(
    base_url="http://localhost:8000/v1",   # your local server
    model="nvidia/Cosmos-Reason2-8B",
    api_key="local",                        # vLLM doesn't enforce; placeholder
    max_tokens=4096,                        # Cosmos recommends 4096 (avoid truncation)
)
brain = Brain(SpatialMemory.open("home.smem", embedding_dim=512), VerbalizerReasoner(vb))
print(brain.ask("where is the mug?"))
```

`strip_reasoning` cleans Cosmos `<think>/<answer>`; with `--reasoning-parser
qwen3` vLLM already returns a clean `content`, so both paths work. See
`examples/02_local_reasoner.py`.

## Notes (verified)

- **Versions:** vLLM ≥ 0.11.0, transformers ≥ 4.57.0. `--trust-remote-code` only
  needed on the NGC vLLM-container path, not the HF-native route.
- **Blackwell:** Cosmos-Reason2 officially supports Hopper/Blackwell (tested
  H100/A100); a dedicated 8B NIM container is published — RTX PRO 6000 runs it.
- **Min VRAM:** 8B needs ≥ 32 GB; the 96 GB card has large headroom.
- **Caveat:** some sources flag vLLM support for Cosmos-Reason2 as evolving —
  confirm the exact vLLM version/recipe on the model's GitHub before deploying.
