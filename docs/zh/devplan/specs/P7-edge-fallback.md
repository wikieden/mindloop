> 🌐 [English](../../../en/devplan/specs/P7-edge-fallback.md) · **中文**

# P7 spec —— 边缘回退：本体离线 AI 链路（LLM + ASR + TTS）

**状态：** 计划中（设计，2026-06-28）。新横切能力；建议里程碑 **M-L3.6**。owner 决策见 §7。

## 1. 目标

网络断时，机器人须靠自身算力保持**认知可用**：**本体**小 LLM + 本地 **ASR**（语音→文本）+
本地 **TTS**（文本→语音）构成自给的 AI 链路。远端大模型是*主*路径；本体链路是**降级回退**
—— 优雅、非对等。关键：离线时机器人**绝不丢失安全与记忆**。

## 2. 离线已天然可用的部分（无需改）

架构本就大部分本地 —— 只有三处碰网络：

| 关注点 | 碰网络? | 为何离线存活 |
|---|---|---|
| **记忆**（tempomem） | 本地 sqlite `.smem` | 从不碰网络 |
| **规划规则**（compile，D3 门控） | 确定性、stdlib | 不碰网络 |
| **技能卡**（Episteme，P2） | 本地 YAML/dict | 不碰网络 |
| **安全**（Phylax，P3） | stdlib 策略 gate | **不碰网络 —— 安全 degrade-closed** |
| **本体派发**（ExecutorAdapter） | 本体 | 不碰网络 |
| Reasoner / Planner LLM | **远端** | ← 需本体回退 |
| 语音输入（ASR） | —（新） | ← 本体引擎 |
| 语音输出（TTS） | —（新） | ← 本体引擎 |

所以 P7 恰好加三项本体能力 + 一条仲裁策略；其余断网即可用。**安全离线存活是头条**：P3 纯
stdlib、跑本体，断网的机器人*更*保守、不是更不安全。

## 3. 本体 AI 链路

```
            在线（网络通）                                离线（网络断）
  麦 ─► [远端 ASR? 或本体] ─► 文本                 麦 ─► 本体 ASR ─► 文本
  文本 ─► Brain.handle ─► Reasoner/Planner          文本 ─► Brain.handle ─► 本体 LLM
              (远端 Cosmos / Qwen)                            (小量化模型，本地)
  Answer/speak ─► [远端/本体 TTS] ─► 音频           Answer/speak ─► 本体 TTS ─► 音频
                                  └──────────── Phylax 安全 gate（本地，恒在） ──────────┘
```

大脑代码**不变**。三处替换走既有/新 seam：

### 3a. Reasoner/Planner failover —— 复用 `Verbalizer` seam

本体 LLM 就是**另一个 `Verbalizer`**，指向本地 OpenAI 兼容服务（vLLM / llama.cpp / MLC /
Ollama 跑在机器人边缘算力）。`CosmosReasonVerbalizer(base_url="http://localhost:<port>/v1",
model=<小>)` 原样可用。

新增：**`FailoverVerbalizer([primary, *fallbacks])`** —— 先试 primary（远端）；遇传输错误
（`QueryError` —— 超时/连接拒绝）回落下一个 backend（本体）。连通性感知 + 滞回防抖。报告哪个
backend 服务（telemetry）。大脑不变 —— 它拿到一个 `Verbalizer`。Reasoner 与
`Planner`/`IntentRouter` 都是 Verbalizer 驱动，一个 wrapper 覆盖整条 LLM 路径。

### 3b. ASR —— 新 `Listener` seam（耳朵）

`mindloop` 发的新协议（同 `ExecutorAdapter` 模式）：`Listener.transcribe(audio) -> str`
（+ 流式变体）。具体本体引擎 BYO（whisper.cpp / sherpa-onnx / Moonshine）。输出喂
`Brain.handle(instruction)`。`MockListener`（脚本化）保持测试无网络。

### 3c. TTS —— 新 `Speaker` seam（嘴）

新协议 `Speaker.say(text) -> Audio`（或流到音频设备）。本体引擎 BYO（piper / kokoro /
sherpa-onnx）。说 `Answer.text`、`plan.speak`、Phylax `refusal_speak`。`MockSpeaker` 记录
话语供测试。

### 3d. 语音回路

薄 orchestrator 串起：`Listener → Brain.handle(..., safety_context) → Speaker`。作小
`voice.py` 回路（或上层 app）；mindloop 拥有 `Listener`/`Speaker` *协议*、非引擎。

## 4. 模式仲裁

`ConnectivityMonitor`（或 failover wrapper 本身）选路径：

- **在线** → 远端大 reasoner（Cosmos-Reason2 / Qwen3.6 工作站）。
- **离线** → 本体小 LLM + 本地 ASR/TTS。
- **滞回** —— 连续 N 次失败才降到离线、连续 N 次成功才回，避免抖动。
- **telemetry** —— 每轮记录哪个模式服务。

## 5. 降级契约（离线 ≠ 在线）

本体模型更弱；离线模式相应收紧：

- **技能卡优先** —— 已知任务优先用 P2 确定性技能卡（无 LLM），小 LLM 是离线*内*的回退。
- **保守安全** —— 离线 `SafetyContext` 默认保守（未知身份→stranger）；Phylax 已强制。
- **更简答案** —— `ask` 可缩 token 预算；离线可禁开放式闲聊。
- **诚实 UX** —— TTS 告知降级（"我离线了，本地处理中"）。

## 6. 边缘硬件与模型候选（推荐）

- **算力** —— 机器人上 NVIDIA Jetson AGX Thor / Orin，或本体板载 GPU。跑本地 OpenAI 兼容服务。
- **LLM** —— 小量化 instruct/VLM：Qwen3-4B/8B 或 Cosmos-Reason2-2B 4-bit，llama.cpp / MLC /
  Ollama / vLLM 服务。
- **ASR** —— sherpa-onnx（流式低延迟）或 whisper.cpp（small/base）或 Moonshine（极小）。均离线跑边缘。
- **TTS** —— piper（快、本地）或 kokoro / sherpa-onnx TTS。

## 7. Owner 决策（待批准）

1. **D-edge-1** —— 本体回退是**降级、非对等**（技能卡优先 + 保守）。确认。
2. **D-edge-2** —— ASR/TTS 作为**新 BYO seam 协议**（`Listener` / `Speaker`），引擎树外 ——
   同 `Verbalizer`/`ExecutorAdapter` 模式。确认。
3. **边缘栈** —— 选本体 LLM、ASR、TTS 引擎 + 边缘算力目标。
4. **ASR/TTS 归属** —— 新包（如 "耳+嘴" 成员）vs 并入 `worldsense`（感知）/ `bodylink`。
   推荐：协议在 `mindloop`，引擎在小新成员或设备包。

## 8. 分期

| 步 | 交付 |
|---|---|
| P7.1 ✅ | `FailoverVerbalizer`（LLM failover，基于调用计数的滞回；无网络测试）—— 2026-06-28 完成。`ConnectivityMonitor` 暂折叠进 wrapper 的 cooldown |
| P7.2 | `Listener` / `Speaker` 协议 + `Mock*` + 语音回路 |
| P7.3 | 参考本体引擎接入（边缘服务 + ASR + TTS），硬件验证 |
| P7.4 | 降级契约 + 模式 telemetry + "离线" UX |

**Exit（M-L3.6）：** 拔网 —— 机器人仍听到命令、规划（技能卡或本体 LLM）、过安全 gate、动作、
说话，全靠自身算力。
