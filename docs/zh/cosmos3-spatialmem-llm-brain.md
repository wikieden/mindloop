> 🌐 [English](../en/cosmos3-spatialmem-llm-brain.md) · **中文**

# 设计 — Cosmos 3 + SpatialMem + LLM 作为具身"大脑"

**状态：** 设计 / 前瞻性（v2，对抗性审查后版本）。
**读者：** 将 SpatialMem 接入具身智能体或视频理解智能体的集成工程师。
**配套文档：** [../02-ARCHITECTURE.md](../../../SpatialMem/docs/zh/02-ARCHITECTURE.md)（SpatialMem
内部架构），[../01-POSITIONING.md](../../../SpatialMem/docs/zh/01-POSITIONING.md)（为什么记忆层
是缺失的一环）。具体感知实现（`Cosmos3PerceptionAdapter`、
相机→世界坐标系几何提升、图像裁剪编码）位于独立的伴随仓库
**`spatialmem-perception`** 中——核心库不负责感知。关于哪些模型需要 SFT/RL
微调（以及哪些保持冻结），请参阅
[post-training-rl-roadmap.md](post-training-rl-roadmap.md)。

> 本文档经过对抗性评审小组审查（架构 / API 准确性 /
> 完整性）。已折入修正：API 签名与已发布代码对齐，
> 并发性声明如实表述，新增安全性 + store 兼容性 + C4 + 错误模型
> 内容。评审过程中发现的一个真实代码 bug（维护性 `commit()` 可能
> 冲刷未融合的待处理观测值）单独追踪，不在本文档讨论范围内。

## 1. 核心论点

具身智能体需要三项能力，而单一模型无法全部提供：

1. **感知 + 物理推理** — 对摄像头当前所见进行理解。
2. **记忆** — 将所见内容**持久化**地保存为结构化、可查询的
   空间形式——跨片段、跨会话、跨天。
3. **推理 / 规划 / 语言交互** — 用通用语言就目标和已记忆的
   世界进行推理。

NVIDIA **Cosmos 3** 提供能力（1）。**SpatialMem** 提供能力（2）。通用 **LLM** 提供
能力（3）。Cosmos 3 的官方技术报告明确点出了能力（2）的缺口——*"时间持久状态、
与对象和智能体绑定的空间锚定……一个可维护的、可操作的场景估计"*——
而其本身并未提供：生成器运行在约 74K token 的有界上下文窗口内，
采用逐请求 KV 缓存，没有跨会话存储。
本设计将三者连接成一个认知闭环。

### 大脑类比（非正式，便于直觉理解）

| 能力 | 组件 | 大脑区域 |
|---|---|---|
| 视觉 + 物理直觉 | Cosmos 3 Reasoner | 视觉皮层 + 小脑 |
| 持久空间/情景记忆 | SpatialMem | 海马体 |
| 语言、规划、抽象 | LLM | 前额叶皮层 |

"大脑"不是任何单一模块——它是将三者绑定在一起的**闭环**。

## 2. 约定（三条总线的统一数据源）

| 量 | 约定 |
|---|---|
| 世界坐标系 | 右手系，单位**米** |
| 位姿 | 4×4 齐次矩阵，**相机→世界** |
| C2/C3 输出中的位置 | 世界坐标系，米 |
| 时间戳 | **float epoch 秒**（与 `node.t_last` 匹配） |
| 姿态角（如有） | 弧度，roll/pitch/yaw |
| 节点标识 | 整型 `node_id`，在读取快照内稳定（§6） |

Cosmos 在推理时**仅看 RGB**。深度 + 位姿由
*adapter* 和 SpatialMem（相机→世界坐标提升）使用，**不**由 Cosmos
Reasoner 使用。

## 3. 架构

```
        ┌─────────────────────────── PERCEIVE ──────────────────────────┐
        │                                                                │
  RGB video ───► Cosmos 3 Reasoner ──┐   depth + pose (SLAM/ARKit/sim)   │
                 (RGB-only, System-2)│           │                       │
                                     ▼           ▼                       │
                          ┌───────────────────────────┐                 │
                          │  Cosmos3PerceptionAdapter  │                 │
                          │  JSON 3D box (cam frame) +  │                │
                          │  pose → world Detection +   │                │
                          │  CLIP-crop feature          │                │
                          └─────────────┬──────────────┘                 │
                                        ▼                                 │
                                 ┌────────────┐                          │
                                 │ SpatialMem │  fuse·persist·hierarchy  │
                                 │ (memory)   │  ·relations·temporal     │
                                 └─────┬──────┘                          │
                       serialize(prompt)│ + query/semantic/spatial tools │
                                        ▼                                 │
                                 ┌────────────┐                          │
                                 │    LLM     │  reason · plan · answer   │
                                 │  (cortex)  │ ◄─ C4 active perception ──┘
                                 └─────┬──────┘   ("look closer at node N")
                                       ▼
                          action / NL answer
                                       └── write-back: update()/history
```

四个契约（§4），一块共享内存，一个 tick（§5），一个并发契约（§6）。

## 4. 接口契约

### C1 · Cosmos 3 → SpatialMem（感知 → 记忆）— *接缝在核心库；adapter 在 `spatialmem-perception`*

核心库仅提供 `PerceptionAdapter` 协议（`add_frame`）。具体的
`Cosmos3PerceptionAdapter` 位于伴随仓库 **`spatialmem-perception`** 中：
Cosmos 接收 **RGB** 并输出结构化的**相机坐标系** 3D 框（JSON：
`label, center, size, orientation`），并可*估计*度量自我位姿；
adapter 将每个框提升为世界坐标系的 `Detection`（使用调用方提供的
位姿，见 §7），并附加 CLIP 裁剪特征——Cosmos 不输出逐对象嵌入。
相机→世界坐标系几何提升和图像裁剪编码器也位于该伴随仓库中。

```python
# shipped API（adapter 是 WIP 部分）：
mem.add_frame(rgb, depth, pose, adapter=cosmos3_adapter)  # adapter.process_frame -> dets -> queue
mem.commit()                                              # 仲裁器跨帧去重
```

### C2 · SpatialMem → LLM（记忆 → 皮层）— *已发布*

序列化的场景图是上下文总线：紧凑、层次化、
关系感知、token 预算受限。

```python
scene = mem.serialize(format="prompt", max_tokens=1500)   # rooms > objects > relations
```

`max_tokens` 是**近似**预算（约 4 字符/token 启发式规则，不是真正的
tokenizer）；它按最新优先顺序丢弃整个顶层子树，并附加
`(N more omitted)` 标记（一个区域绝不会在没有其内容的情况下出现）。
留出余量以应对模型实际 tokenizer 的偏差。

### C3 · LLM ↔ SpatialMem（皮层将记忆作为工具查询）— *已发布：`spatialmem.SpatialMemTools`*

C2 和 C3 是**同一个**记忆访问接缝的两种访问模式：对小型场景传入完整
序列化图（C2），对大型场景让 LLM 按需拉取（C3）。两者读取的是**同一个
每轮快照**（§6），因此被引用的 `node_id` 在该轮内始终有效。

建议的工具接口（薄封装；底层方法均已发布）：

| 工具 | 映射到（已发布） | 状态 |
|---|---|---|
| `spatial_query(near, radius_m)` | `mem.spatial(...)` | 已发布函数 |
| `semantic_search(text, k)` | `mem.semantic(...)` | 已发布函数 |
| `whats_in(region)` | `mem.contents(region)` | 已发布函数 |
| `whats_on(anchor)` | `mem.query("what's on the …")` | 已发布函数 |
| `recent_changes(since_ts)` | `mem.changes(since_ts)` / `mem.moved()` | 已发布函数 |
| `serialize_scene(max_tokens)` | `mem.serialize(...)` | 已发布函数 |

具体工具 schema（一个示例；其他结构相同）：

```json
{
  "name": "semantic_search",
  "description": "Find remembered objects matching a text query.",
  "parameters": {
    "type": "object",
    "properties": {
      "text":  {"type": "string", "description": "e.g. 'coffee mug'"},
      "k":     {"type": "integer", "default": 5}
    },
    "required": ["text"]
  }
}
```

返回信封（每个工具统一格式），使 LLM 能够**引用** id（防幻觉）：

```json
{"hits": [
  {"node_id": 42, "label": "mug", "centroid_m": [1.2, 0.3, 0.9],
   "confidence": 0.87, "t_last": 1.748e9}
]}
```

`near` 接受 `node_id`、标签或 `[x,y,z]`（世界坐标系，米）；`radius_m`
单位为米；`since_ts` 为 float epoch 秒。

### C4 · LLM → Cosmos 3（主动感知）— *提案阶段，有界*

当记忆不确定时（低置信度节点、陈旧区域），LLM 可请求
Cosmos 重新观察。C4 是**有界**请求，不是开放循环：

- **目标表示：** `node_id` 或世界 bbox → 解析为*所需相机位姿*；
  若目标当前不可达（不在视野内、机器人无法到达），
  以一等公民结果返回 `target_unreachable`，不阻塞。
- **预算：** 每个 tick 和每个节点的最大重看次数；超出上限 →
  带有明确不确定性声明的回答。
- **环路中断器：** 一个节点在经过 *k* 次重看后仍保持低置信度，
  进入冷却期，直到新证据到来前不再被重新请求。
- **失败处理：** Cosmos 超时 / 输出格式错误 → 降级为"基于现有记忆推理，
  标记数据陈旧"；绝不阻塞推理循环。

## 5. 部署拓扑

### 拓扑 A — Cosmos Reasoner *即* LLM（单 VLM 大脑）

Cosmos 同时负责感知和最终推理/回答；SpatialMem 是片段间的记忆。
全 NVIDIA，接线最简单，GPU 需求大。使用已发布的
`CosmosReasonVerbalizer` 作为 `answer()` 后端——**当前默认为
Cosmos Reason 2（`nvidia/cosmos-reason2-8b`）**，可通过 `model=` 参数
配置为 GA 版 Cosmos 3 Reasoner NIM。

### 拓扑 B — 独立通用 LLM（推荐默认）

Cosmos 仅负责感知（C1）。自带 LLM（Claude/GPT/Llama/Ollama）基于
序列化图进行推理（C2）并调用记忆工具（C3）。更灵活，推理成本更低，
无厂商锁定；与 SpatialMem 的 BYO-`Verbalizer` 设计理念一致。

| | A（Cosmos = 大脑） | B（独立 LLM） |
|---|---|---|
| 推理质量 | 物理 AI 调优 | 最佳通用 LLM |
| 成本 / 延迟 | 每个推理步骤消耗 GPU | 廉价文本 LLM |
| 厂商锁定 | NVIDIA | 无（BYO；可本地 Ollama） |
| 接线复杂度 | 最简单 | 多一个组件 |

## 6. 并发与一致性契约（v0 = 单线程）

**关于当前代码行为的如实说明：** `SpatialMemory` 封装了一个
同步 `sqlite3.Connection`。它**不是**线程安全的；调用方**必须
串行化所有访问**。`add_frame()` **内联**运行 `adapter.process_frame()`
——会为 Cosmos 的秒级/片段延迟阻塞调用方。目前尚无工作线程
或异步摄入队列。

不变量：
- **待处理观测值存在时不执行维护操作。** `add_detections()` 将融合
  推迟到 `commit()`；不要在 `add_detections()` 和 `commit()` 之间调用
  `decay()/consolidate()/relate()/update()/define_region()/forget()`。
  （强制执行此约束的代码修复单独追踪。）
- **每轮读取快照。** 推理轮次应为其所有 C2 序列化 + C3 工具调用
  读取同一快照，以防感知提交发生在轮次中途时 `node_id` 悬空
  （一个节点可能在两次工具调用之间被 consolidate/decay 合并/拆分/剪除）。

**未来规划（尚未发布）：** 有界摄入队列 + 专用写连接 +
每个查询线程的 WAL 读连接，可让感知（采样）和
推理（按需）真正在独立节奏下运行。在此之前，
"慢眼睛 / 按需皮层"的解耦是调用方的**调度纪律**，
而非来自库的并发保证。

## 7. 认知 tick（时序）

```
on new keyframe(s) + pose:
  1. PERCEIVE  dets = cosmos3_adapter.process_frame(rgb, depth, pose)  # System-2, sampled
  2. REMEMBER  mem.add_detections(dets); stats = mem.commit()         # fuse/dedup (atomic)
               changes = mem.changes(last_commit_ts)                  # positional arg
  3. (between ticks, never mid-ingest) mem.consolidate(); mem.decay() # hygiene
on goal / question:
  4. RETRIEVE  ctx = mem.serialize(format="prompt", max_tokens=B)  +  query()/semantic()
  5. REASON    out = llm(ctx, goal, tools=[C3 tools])                # plan / answer (cite ids)
  6. ACT       execute(out)  |  return answer
  7. WRITE-BACK if correction: mem.update(node_id, ...)              # close the loop
```

感知（1–2）在**采样关键帧节奏**下运行（Cosmos 是秒级/片段，
非逐帧）。推理（4–6）按需运行。记忆是慢眼睛与按需皮层之间的缓冲——
但在 v0 中两者运行在*同一线程*（§6）。

**时钟说明：** `changes()`/`stale()` 以观测时间戳为键。每次提交使用
同一个权威时钟并一致传递 `det.ts`（若 `det.ts` 为 `None` 则回退到
摄入墙钟时间——不要在同一批次中混用片段时间和墙钟时间）。
`moved()` 测量首次↔末次位移（净位移，非近期运动）——在展示
"什么移动了"时请注意这一点。

## 8. 为何需要三者（消融分析）

| 移除 | 破坏的内容 |
|---|---|
| − Cosmos 3 | 无感知 / 无法从原始视频中获得 3D 空间锚定 |
| − SpatialMem | 无持久化；跨片段/会话遗忘（Cosmos 自身的缺口）；LLM 每次都需重读原始帧，耗尽上下文窗口 |
| − LLM | 无法对已记忆的世界进行通用规划 / 语言理解 / 抽象推理 |

## 9. 跨会话的 store 兼容性

"跨片段、会话、天"的持久化存在真实的硬性约束：

- **`embedding_dim` 在创建时锁定。** 以不同编码器（CLIP-512 vs SigLIP-768）
  重新打开会抛出 `SchemaMismatchError`。"跨会话记忆"要求**永远使用同一个编码器**；
  Cosmos adapter 的 CLIP 裁剪特征使编码器成为一个不可变的关键选择。
  如需更换：将数据重新嵌入到新的 store 中。
- **仅向前的 schema**（`SCHEMA_VERSION`，migrations 目录）：由较新库版本
  写入的 store 无法在旧版本上打开。对长期 store 请锁定库版本。
- **`aux` 不是列。** adapter 输出 `aux={source, orient, box2d}`，但
  `nodes`/`observations` 没有 `aux` 列 → 朝向/box2d **在持久化时丢失**。
  在 schema 升级添加 JSON `aux` 列之前，跨会话的回答无法依赖 3D 朝向信息。

## 10. 安全性

| 攻击面 | 风险 | 缓解措施 |
|---|---|---|
| 场景文本 → LLM 提示 | **提示注入** — 对象标签来自用户无法控制的视频，并被原样传入 `to_prompt()` 再流向 LLM；`"ignore prior instructions…"` 这样的标签加上 C3 工具访问权限构成数据外泄向量 | 在提示中转义/分隔不可信场景文本；白名单控制注入指令可访问的 C3 工具；将工具参数视为不可信输入 |
| 数据外泄 | `CosmosReasonVerbalizer` 使用 Bearer token 将序列化场景 POST 至 `integrate.api.nvidia.com`；拓扑 A/B 均将场景数据**发往外部** | 向用户明确说明；为敏感部署提供本地路径（Ollama / 自托管 NIM） |
| API 密钥 | `NVIDIA_API_KEY`（及 BYO-LLM 密钥） | 仅通过环境变量传入；绝不持久化到 `.smem`；在日志中脱敏 |
| Cosmos 输入视频 | 不可信媒体 | 视为不可信输入；验证帧的 shape/dtype |

## 11. 错误处理与降级

架构最强的特性——**当感知或推理不可用时，记忆能优雅降级**——
必须明确定义并加以测试：

| 组件故障 | 行为 |
|---|---|
| Cosmos NIM 超时 / JSON 格式错误 | adapter 抛出异常，**跳过该帧**，记录日志，继续服务现有记忆 |
| 编码器缺失 | 在**接线时**快速失败，而非逐帧失败（特征是必要的） |
| BYO-LLM 不可达 / 工具调用格式错误 | 重试策略 → 回退到原始 `serialize()` 输出 |
| `commit()` 超时（实际 `timeout_s=30`） | 定义好的异常接口；调用方重试或丢弃该批次 |

## 12. 非目标

继承 SpatialMem 的非目标：**不是** SLAM（位姿由上游提供），**不是**动作 /
运动规划层（由消费方/LLM 负责），**不是**新的 VLM。
**v0 是单摄像头、单智能体。** 多摄像头/多智能体需要本设计尚不具备的原语：
逐观测的摄像头/智能体来源标注、单写者协调方案（未来 gRPC/服务外观负责写；
智能体作为客户端）、每来源独立的待处理缓冲区，以及跨智能体的外参标定。
这些在落地之前均不在范围之内。

## 13. 情景表征（时间 + 地点）

§15 的评估指标依赖情景记忆，因此在此明确定义：

- **episode（情景）= 一次会话运行**（store 建模为 `episodes(id, session,
  start_ts, end_ts)`；节点携带 `t_first/t_last`）。
- 时间范围 + 空间范围检索：`whats_in(region, at_ts=…|episode=…)` 工具，
  以及 `serialize()` 渲染过去某时刻的快照或**与当前的 delta**。
- 这是"片段 1 中看到的对象，在片段 9 中被询问"评估所使用的查询路径。

## 14. 可观测性

一个错误的回答横跨三个黑盒，因此需要在
PERCEIVE→REMEMBER→REASON→ACT 全链路贯穿一个 **tick/trace id**。
记录每次 C3 工具调用（名称、参数、返回的 `node_id` 列表、延迟）。
记录溯源链：LLM 回答 → 被引用的 `node_id` → 源观测值/检测结果 → Cosmos 片段。
接入现有的 `mem.stats()` / `mem.dump()` / `spatialmem.events` 日志。

## 15. 构建阶段

| 阶段 | 交付物 | 状态 |
|---|---|---|
| P0 | `CosmosReasonVerbalizer`（回答后端，当前使用 Cosmos Reason 2） | ✅ 已发布（核心库） |
| P1 | `Cosmos3PerceptionAdapter`（C1）+ 几何提升 + `ImageEncoder`——需要 GPU + schema 探测 | ⬜ 在 `spatialmem-perception` |
| P2 | 记忆即工具（C3）——`SpatialMemTools`（schema + 调度，参数已验证） | ✅ 已发布 |
| P2+ | 封装 `SpatialMemTools` 的轻量 MCP 服务器 | ⬜ |
| P3 | 主动感知循环（C4）——有界 | ⬜ |
| P4 | 端到端智能体演示：流式场景 → 带记忆的多轮规划 | ⬜ |

## 16. 评估

- 复用 `bench.recall_at_k` 评估检索质量。
- **"记忆优势"评估：** 仅凭跨片段/跨会话持久化才能回答的问题
  （片段 1 中看到的对象，在片段 9 中被询问）——仅用 Cosmos（有界上下文）
  会失败；Cosmos+SpatialMem 通过。这个数字证明的是架构，而非单个组件。
- **每 tick 的延迟预算**，分别报告：感知（采样）、
  推理（按需），以及**维护**（`consolidate()` 是 O(n²)，
  `candidates_near()` 在计划中的 R-tree 到位之前是线性 AABB 扫描——
  维护是跨"天"扩展代价最大的部分）。

## 17. 成本模型（粗略估算，用于支撑"B 是默认"的决策）

假设每 5 秒 1 个关键帧片段，serialize 预算 1500 token：

- **Cosmos（感知）：** 通过 NIM 的每片段成本，或自托管
  Nano 16B（工作站）/ Super 64B（数据中心）按 GPU 小时摊销；
  对关键帧/事件设门控以控制成本。Edge（约 4B）**尚未发布**。
- **推理，拓扑 B：** 约 1500 输入 + 数百输出 token × 所选 LLM 的 $/Mtok，
  **每次提问**（而非每帧）→ 通常远低于感知成本。
- **拓扑 A：** 每次提问在 GPU 上执行一个 System-2 VLM 推理步骤 →
  成本明显高于拓扑 B 的文本 LLM；这是 B 作为默认拓扑的核心原因。

（确定目标模型后，代入实际的每模型定价。）

## 18. 工作示例（拓扑 B，使用真实已发布方法）

```python
import numpy as np
from spatialmem import SpatialMemory

def stub_llm(context: str, question: str) -> str:        # swap for Claude/GPT/Ollama
    return f"(reasoning over)\n{context}\nQ: {question}"

mem = SpatialMemory.open("home.smem", embedding_dim=512, encoder=my_clip)
# C1: Cosmos-perceived detections (here: pre-made) -> fuse
mem.add_detections([det_mug, det_table]); mem.commit()
# C2: serialize for the cortex
ctx = mem.serialize(format="prompt", max_tokens=1500)
# C3 (proposed wrapper) would expose query/semantic/spatial as tools; shipped today:
hits = mem.semantic("coffee mug")                        # -> [NodeHit(node_id=…, …)]
# REASON (Topology B): BYO LLM over ctx + tool results, cite node ids
print(stub_llm(ctx, "where is the mug?"))
# or one-shot via the shipped verbalizer path:
# mem = SpatialMemory.open("home.smem", embedding_dim=512, encoder=my_clip, verbalizer=cosmos_vb)
# print(mem.answer("where is the mug?"))
```

## 19. 一段话总结

> Cosmos 3 感知并对视频片段进行物理推理；SpatialMem 将所见内容
> 记忆为持久化、可查询的 3D 场景图；LLM 基于该记忆进行规划和语言交互。
> Cosmos 感知，SpatialMem 记忆，LLM 思考——
> 而 NVIDIA 自家旗舰报告已明确指出，这颗海马体目前仍然缺失。
