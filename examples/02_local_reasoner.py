"""Local reasoner — point CosmosReasonVerbalizer at a self-hosted OpenAI endpoint.

Start a server first (see docs/local-serving.md), e.g. on an RTX PRO 6000:

    vllm serve nvidia/Cosmos-Reason2-8B --reasoning-parser qwen3 --port 8000

Then: python examples/02_local_reasoner.py
Needs a running server at BASE_URL; prints guidance (does not crash) if it is
unreachable, so this is safe to run without a GPU.
"""

from __future__ import annotations

import pathlib
import tempfile

import numpy as np

from spatialmem import Detection, QueryError, SpatialMemory
from spatialmem_brain import Brain, CosmosReasonVerbalizer, VerbalizerReasoner

BASE_URL = "http://localhost:8000/v1"
MODEL = "nvidia/Cosmos-Reason2-8B"
DIM = 16


def _det(label: str, center: tuple[float, float, float], seed: int) -> Detection:
    rng = np.random.default_rng(seed)
    cx, cy, cz = center
    return Detection(
        label=label,
        feature=rng.standard_normal(DIM).astype("float32"),
        center_xyz=center,
        bbox_min=(cx - 0.05, cy - 0.05, cz - 0.05),
        bbox_max=(cx + 0.05, cy + 0.05, cz + 0.05),
        confidence=0.9,
        ts=1000.0,
    )


def main() -> None:
    vb = CosmosReasonVerbalizer(base_url=BASE_URL, model=MODEL, api_key="local", max_tokens=4096)
    path = pathlib.Path(tempfile.mkdtemp()) / "room.smem"
    with SpatialMemory.open(path, embedding_dim=DIM) as mem:
        brain = Brain(mem, VerbalizerReasoner(vb))
        brain.ingest([_det("mug", (1.2, 0.0, 0.94), 1), _det("table", (1.4, 0.0, 0.75), 2)])
        try:
            ans = brain.ask("where is the mug?")
        except QueryError as e:
            print(f"No local server at {BASE_URL}? Start one first (docs/local-serving.md).")
            print(f"  detail: {e}")
            return
        print("answer:", ans.text)
        print("cited node ids:", ans.cited_node_ids)


if __name__ == "__main__":
    main()
