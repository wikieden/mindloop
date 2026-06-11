> 🌐 [English](README.md) · **中文**

# spatialmem-brain

**[SpatialMem](https://github.com/wikieden/spatialmem)** 的**大脑 / LLM 层** ——
将记忆 + 推理（+ 可选感知）绑定成一个认知循环。

> **为什么要单独建一个仓库？** SpatialMem 核心是*记忆*（海马体），
> 保持纯 numpy 依赖，仅暴露协议接缝。具体的 LLM 集成
> 与编排——即*大脑*——就在这里，就像感知功能放在
> `spatialmem-perception` 一样。核心发布 `Verbalizer` 协议；本仓库发布
> 填充该协议的模型以及驱动它的循环。

## 内容一览

| 组件 | 职责 |
|---|---|
| `Brain` | 认知循环：`observe`/`ingest`（感知 → 记忆）+ `ask`（检索 → 推理） |
| `Reasoner` 协议、`VerbalizerReasoner`、`ScriptedReasoner` | 将问题 + 序列化场景转换为带引用的 `Answer` |
| `CosmosReasonVerbalizer` | 以 NVIDIA Cosmos Reason NIM 作为 `answer()` 后端（仅用标准库） |
| `Answer`（`text` + `cited_node_ids`） | 引用记忆节点 id 的有根据回复 |

## 架构

```
RGB(-D) ─► [spatialmem-perception adapter] ─► Detections
                                               │
                                               ▼
                                   spatialmem (memory: fuse/persist/query)
                                               │ serialize
                                               ▼
                       Brain.ask ─► Reasoner (LLM) ─► Answer(text, cited ids)
```

完整系统设计：[docs/cosmos3-spatialmem-llm-brain.md](docs/zh/cosmos3-spatialmem-llm-brain.md)。
生产版三层大脑（慢思考 / 习惯 / 反射）—— 提案与决策记录：
[docs/brain-architecture.md](docs/zh/brain-architecture.md)。

## 安装

```bash
pip install spatialmem-brain                 # 记忆 + 推理
pip install spatialmem-brain[perception]     # + spatialmem-perception（感知眼）
```

（`spatialmem` 是核心依赖；`spatialmem-perception` 是可选的
完整栈扩展。）

## 快速上手（拓扑 B — 自带 LLM）

```python
from spatialmem import SpatialMemory
from spatialmem_brain import Brain, VerbalizerReasoner, CosmosReasonVerbalizer

mem = SpatialMemory.open("home.smem", embedding_dim=512)
brain = Brain(mem, VerbalizerReasoner(CosmosReasonVerbalizer(model="nvidia/cosmos-reason2-8b")))
brain.ingest(detections)                 # 记忆（自带感知）
print(brain.ask("where is the mug?"))    # 检索 -> 推理 -> 带引用的 Answer
```

测试使用 `ScriptedReasoner`（确定性，无需网络）。

## 自托管推理器

将 `CosmosReasonVerbalizer(base_url=...)` 指向本地 OpenAI 兼容服务器
（vLLM 或 NVIDIA NIM 容器）——例如在 RTX PRO 6000
（96 GB）上运行 Cosmos-Reason2-8B。分步说明（变体、显存、启动命令、接线）：
**[docs/local-serving.md](docs/zh/local-serving.md)**。可运行骨架：
`examples/02_local_reasoner.py`。

## 许可证

Apache-2.0 — 详见 [LICENSE](LICENSE)。
