> 🌐 [English](../en/local-serving.md) · **中文**

# 本地推理器部署（自托管 Cosmos Reason）

在自己的 GPU 上运行推理器，而不依赖 NVIDIA 托管网关。
`CosmosReasonVerbalizer` 与任何 **OpenAI 兼容** 的 `/v1/chat/completions`
端点通信，因此只需启动一个本地服务器并将 `base_url` 指向它——无需修改代码。

已针对 NVIDIA 一手资料（Cosmos-Reason2 GitHub、HF model card、NIM 文档）
进行验证，适用于单卡 **RTX PRO 6000 Blackwell（96 GB）** 工作站。

## 选择变体（BF16；权重大小 ≈ 参数量 × 2 字节）

| 模型 | 权重大小 | 96 GB 上的余量 | 使用场景 |
|---|---|---|---|
| **`nvidia/Cosmos-Reason2-8B`** | ~17 GB | ~75 GB 空闲，完整 256K ctx | **默认** — 标准推理器，速度快 |
| `nvidia/Cosmos-Reason2-32B` | ~67 GB | ~25–29 GB 空闲 → 16–64k ctx；256k 需 FP8 | 最高推理质量 |
| `nvidia/Cosmos-Reason2-2B` | ~5 GB | 极小 | 边缘设备 / 高并发 |
| `nvidia/Cosmos3-Nano`（16B） | ~32 GB | NVIDIA 官方 RTX-PRO-6000 推荐配置 | 全能模型（推理器+生成器）；比纯文本推理器更重 |

对于 `answer()` 后端的纯文本推理器，**Cosmos-Reason2-8B** 是最务实的选择。
Cosmos 3 Nano 是完整的双塔世界模型——仅在同时需要世界/动作生成时才选用。

## 方案一 — vLLM（自托管，推荐）

```bash
pip install "vllm>=0.11.0" "transformers>=4.57.0"   # Cosmos-Reason2 已集成进 transformers，无需 --trust-remote-code
vllm serve nvidia/Cosmos-Reason2-8B \
  --max-model-len 16384 \
  --reasoning-parser qwen3 \
  --media-io-kwargs '{"video": {"num_frames": -1}}' \
  --gpu-memory-utilization 0.90 \
  --port 8000
# 验证：  curl http://localhost:8000/v1/models
```

在 `:8000` 上启动 OpenAI 兼容服务器（`/v1/chat/completions`）。如需 32B 模型的
256k 上下文：添加 `--quantization fp8`（Blackwell 原生支持）可将权重降至约 33 GB。
（Cosmos 3 Nano 为 **BF16 only** — 官方不支持 FP8/FP4/FP16。）

## 方案二 — NVIDIA NIM（开箱即用容器）

```bash
docker login nvcr.io        # username: $oauthtoken   password: <NGC_API_KEY>
export NGC_API_KEY=<your_ngc_key>
mkdir -p ~/.cache/nim
docker run --rm --runtime=nvidia --gpus all --shm-size=32GB \
  -e NGC_API_KEY -v ~/.cache/nim:/opt/nim/.cache -u "$(id -u)" \
  -p 8000:8000 nvcr.io/nim/nvidia/cosmos-reason2-8b:1.6.0
# 请求时的 model id: "nvidia/cosmos-reason2-8b"；端点为 /v1/chat/completions
```

部署前请在 NGC 目录（`catalog.ngc.nvidia.com/.../cosmos-reason2-8b`）确认是否有比 `1.6.0` 更新的镜像标签。

## 接入（一行代码 — `base_url`）

```python
from tempomem import SpatialMemory
from mindloop import Brain, VerbalizerReasoner, CosmosReasonVerbalizer

vb = CosmosReasonVerbalizer(
    base_url="http://localhost:8000/v1",   # 本地服务器地址
    model="nvidia/Cosmos-Reason2-8B",
    api_key="local",                        # vLLM 不强制校验；此处为占位符
    max_tokens=4096,                        # Cosmos 建议 4096（避免截断）
)
brain = Brain(SpatialMemory.open("home.smem", embedding_dim=512), VerbalizerReasoner(vb))
print(brain.ask("where is the mug?"))
```

`strip_reasoning` 会清理 Cosmos 的 `<think>/<answer>` 标签；使用 `--reasoning-parser
qwen3` 时，vLLM 已返回干净的 `content`，两种方案均可正常工作。参见
`examples/02_local_reasoner.py`。

## 注意事项（已验证）

- **版本要求：** vLLM ≥ 0.11.0，transformers ≥ 4.57.0。`--trust-remote-code` 仅在
  NGC vLLM 容器路径下需要，HF 原生路由不需要。
- **Blackwell 支持：** Cosmos-Reason2 官方支持 Hopper/Blackwell（已在 H100/A100 上测试）；
  已发布专用 8B NIM 容器——RTX PRO 6000 可运行。
- **最低 VRAM：** 8B 需要 ≥ 32 GB；96 GB 显卡余量充足。
- **注意事项：** 部分资料指出 vLLM 对 Cosmos-Reason2 的支持仍在迭代中——
  部署前请在模型的 GitHub 上确认确切的 vLLM 版本和使用方式。
