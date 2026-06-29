> 🌐 [English](../../en/devplan/DEV-PLAN.md) · **中文**

# mindloop L3 大脑 —— 开发计划

**范围：** 把 L3 认知大脑（`mindloop`）从问答回路，建成已拍板决策描述的完整 S2 编排器。
**L1/L2（执行、真机）暂缓 —— 其设计复用 Brain2Robot 既有 L2/L1 工作**（owner，2026-06-15）。
`bodylink` 的 `MockBody`（现还有 Genesis 仿真 backend）在整个 L3 开发中代替本体。

**依据：** 决策 D1–D5 + K1–K3（brain-architecture.md §9，2026-06-15 拍板）与本体契约
B1–B10（§11，2026-06-11 拍板）。每阶段**先参考对应 Brain2Robot 设计文档**（长期指令 ——
B2R 是原型产品）。

**状态（2026-06-28 更新）：** P0–P5 已发 + P7.1 已发。**M-L3.1 ✅、M-L3.2 ✅、M-L3.3 ✅**
（完整 S2 回路端到端复现）。每阶段先写 spec、验证后才算 done。大脑测试套：85 个网络隔离测试，
ruff 清，pyright 0。

---

## 0. 原则（每阶段适用）

- **只 L3。** mindloop 拥有 S2（意图→规划→重规划→对话）+ Phylax 策略层 + 协议 seam。执行、
  符号-BT 安全、真机不归（D1）—— 复用 B2R / 交 `bodylink`。
- **大脑核心仅 stdlib。** 重依赖（LLM 客户端、encoder）放 extra 或外部端点后。
- **测试无网络。** 每阶段对 `ScriptedReasoner` + `MockBody` + hash encoder + 注入 fake 测 ——
  绝不真 LLM 或模型下载。
- **接地 + 审计。** 计划绑对象槽位到场景图 node id；答案引用 node id；每次派发入 L4 痕迹。
  审计链不断（B9）。
- **先参考 B2R。** 每阶段标注所移植 B2R 文档。
- **双语文档、Conventional Commits、每改动 CHANGELOG、ruff + pyright 闸** —— 同 tempomem 核标准。

---

## 1. 当前状态

**大脑脊柱已贯通至 P4。** `Brain.handle` 跑 route → plan → compile（D3 门控）→ policy（P3 门控）
→ dispatch → 有界重规划（P4），每步入痕迹。

| 能力 | 状态 | 位置 |
|---|---|---|
| `Brain.ingest` / `Brain.ask`（带引用 Answer） | ✅ | `brain.py` |
| `Reasoner`/`Verbalizer` 协议 + Scripted/Verbalizer/CosmosReason + **`FailoverVerbalizer`** | ✅ | `reason.py`, `verbalizers.py` |
| 执行器 seam：`SubTask`/`StatusUpdate`/`CapabilityManifest` + 类型 `ErrorCode`/`RecoveryHint` | ✅ P0 | `execute.py` |
| 意图路由 + 两段式规划（LLM 动词 → 规则编译） | ✅ **P1 / M-L3.1** | `plan.py` |
| Episteme 技能卡库 | ✅ **P2** | `episteme.py` |
| Phylax 语义策略层 | ✅ **P3** | `phylax.py` |
| L4 痕迹 + 有界重规划 | ✅ **P4** | `trace.py`, `replan.py` |
| 多轮对话 + L5 偏好叠加（完整回路端到端复现） | ✅ **P5 / M-L3.3** | `dialogue.py`, `preference.py`, `brain.py` |
| Reasoner/planner LLM failover（离线 AI 链路第 1 步） | ✅ **P7.1** | `verbalizers.py` |

**下一个：** **P6**（把 ScriptedReasoner 换成生产 Cosmos-Reason2 + 评测 harness；云→Thor 切换）。
P7.2+ 与 D3 本体轨并行。

> **并行 D3 本体适配轨**（在 `bodylink`，不在本大脑计划）：多机型 manifest 目录
> （g1d/h1/gr1/arm6）、`BaseExecutorAdapter` SDK、一致性套件、Genesis 物理仿真 backend
> （主机 + mac 验证）全已发。真硬件 adapter + 符号-BT/反射 Phylax 层待做。见
> [TECH-DESIGN](../../../../docs/zh/TECH-DESIGN.md) 与
> [bodylink 多机型设计](../../../../bodylink/docs/zh/multi-model-adaptation-design.md)。

---

## 2. 阶段图

```
P0 ✅ ─► P1 ✅ ─► P2 ✅ ─► P3 ✅ ─► P4 ✅ ─► P5 ✅ ─► P6 ▢          P7 ▢ (P7.1 ✅)
 seam     S2 脊柱   技能     策略    痕迹+    完整     生产          边缘回退
                                    重规划    回路    (LLM+eval)    (离线链路)
```

| 阶段 | 主题 | 里程碑 | 状态 |
|---|---|---|---|
| P0 | Seam 契约 + 测试脚手架 | — | ✅ |
| P1 | 意图路由 + 规划骨架 | M-L3.1 | ✅ |
| P2 | Episteme 技能卡库 | M-L3.2 | ✅ |
| P3 | Phylax 策略层 | M-L3.2 | ✅ |
| P4 | L4 痕迹 + 重规划 | M-L3.3 | ✅ |
| P5 | 对话 + 完整 S2 回路 | M-L3.3 | ✅ |
| P6 | 生产推理器 + 评测 + 云启动 | M-L3.4 | ◐ 评测 + 真 LLM 驱动完成；Thor 待硬件 |
| P7 | 边缘回退 —— 本体离线 AI 链路（LLM+ASR+TTS） | M-L3.5 | ◐ P7.1+P7.2 完成 |

---

## 3. 各阶段

### P0 —— Seam 契约 & 测试脚手架  ·  ✅ DONE (2026-06-16)

冻结 L3 规划所对的协议：`ExecutorAdapter` + 值类型（`execute.py`，开放词汇动词 D3、
node-id 携带/回显 B9、类型化错误/恢复 B3、两层 manifest D3）、`PreferenceStore` 桩（L5）、
`HealthReport`/`Brain.health()`（B5），以及带 `MockBody` + `g1d_manifest()`（B10）的
`bodylink` 成员。契约测试通过。

> `bodylink` 是**工作区跟踪目录**（根仓库），尚非独立 GitHub 仓/子模块。发布前毕业（需 owner
> 放行 —— 对外动作）。§8 追踪。

### P1 —— 意图路由 + 规划骨架  ·  ✅ DONE (2026-06-26)  ·  M-L3.1

**Spec：** [specs/P1-intent-planning.md](specs/P1-intent-planning.md)。两段式 B2R-MVP 格式：
LLM 出文本动词序列 → `compile_commands` 确定性填 `SubTask` 元数据、绑对象到 node id（B9）、
拒本体 manifest 没有的动词（D3）。`IntentRouter` + `Planner`（Verbalizer 驱动 + Scripted）。
`Brain.handle` 编排 route → ask | plan+dispatch。8 测试；对真 Cosmos-Reason2 端点交叉验证。
**线上无规则规划回退**（§1a）。

### P2 —— Episteme 技能卡库  ·  ✅ DONE (2026-06-28)  ·  M-L3.2  ·  K2

**Spec：** [specs/P2-episteme-skill-cards.md](specs/P2-episteme-skill-cards.md)。程序性知识即
数据：`SkillCard` = 扁平步骤 + 规则（K2；DAG 经 `schema_version` 预留）。`instantiate()` 触发
情境匹配规则、叠加 L5 偏好、按 manifest 门控动词（D3）→ 出**与 LLM 规划器相同的 `Command` IR**。
BYO-encoder 检索；`SkillCardPlanner` 库优先、LLM 回退标低置信。带洗衣 + 烹饪卡（对 MockBody
端到端）。需给本体 manifest 加 `operate_appliance` 动词。

### P3 —— Phylax 策略层  ·  ✅ DONE (2026-06-28)  ·  M-L3.2  ·  D4 顶层

**Spec：** [specs/P3-phylax-policy.md](specs/P3-phylax-policy.md)。大脑侧**语义**安全层（BT +
反射层推迟）。声明式 `Policy`（adult-only 动词、需监督动词、禁区 node id、近人限速、可信卡
provenance）按 `SafetyContext` 经 `Phylax.check` 审，在 `handle()` 里 compile 与 dispatch
**之间**跑。任一 violation **阻断整个 plan** —— 停+说、不重路由/重试（B2R §9"上层想做永不覆盖
下层不可以"）。`SkillCardPlanner` 拒 untrusted `safety:` 卡。移植 B2R `safety_architecture.md`
§2/§8/§9。

### P4 —— L4 痕迹 + 重规划  ·  ✅ DONE (2026-06-28)  ·  M-L3.3  ·  D2 + B3

**Spec：** [specs/P4-trace-replanning.md](specs/P4-trace-replanning.md)。

- **L4 `TraceStore`**（`trace.py`）—— 只增 stdlib-sqlite 情节日志，记每次尝试+失败、引用场景
  node id（B9）；可按 node/session 查、`failures()` 视图、永不删（清=轮换 `session_id`）。
  **暂在 `mindloop`**；D2 设想的并入 tempomem **核心**推迟到跨仓协调改动（§8 追踪）——
  引用 node id 已满足共享 id 空间要求。
- **`Replanner`**（`replan.py`）—— 类型化 FAILED `StatusUpdate`（B3）→ **有界**修复 `SubTask`
  序列（编译后、复用 node id）：RETRY / ADJUST（offset/relax/force）/ REROUTE（导航+重发）/
  SKIP / ESCALATE。上限：每(verb,node) ≤2 + 全局 ≤6 → 触顶升级（停+说，无死循环）。
  `Brain(replanner=, trace=)` 把派发变有界重规划回路；修复序列派发前**经 Phylax(P3) 重审**。

### P5 —— 对话 + 完整 S2 回路  ·  ✅ DONE (2026-06-28)  ·  M-L3.3

**Spec：** [specs/P5-dialogue-full-loop.md](specs/P5-dialogue-full-loop.md)。回路 P4 时已串通；
P5 给它包上**多轮对话**（`dialogue.py` —— `Conversation` 把近期轮次穿进 `ask`，让追问对前文解析）
和 **L5 偏好叠加**（`PreferenceStore.all` + 具体 `DictPreferenceStore`；`Brain.handle(person=)`
把某人偏好叠到编译后 plan 的 params、manifest 门控）。`Brain.converse` 跑一轮并记录。**关 M-L3.3**
—— 端到端场景测试：一段对话走 问答 → 任务成功 → 任务重规划→恢复 → 任务安全阻断，全引用+全痕迹、
无真网络。

### P6 —— 生产推理器 + 评测 + 云启动  ·  ◐ (评测 harness 完成)  ·  M-L3.4  ·  B6

**目标：** 把 ScriptedReasoner 换成真 LLM；测量；部署。

- **✅ 评测 harness**（`eval.py`，网络隔离）—— `run_eval` 对脚本场景打分：规划准确率、策略合规、
  重规划成功率、引用合规；`EvalThresholds` 提议阈值（§8）。客观脚手架就位，可对任何接入的 reasoner 跑。
- **✅ 真 LLM 驱动已验证（2026-06-28）** —— 完整 S2 回路对 RTX PRO 6000 主机上的生产模型
  端到端跑通：**Cosmos-Reason2-8B**（:8002）作推理器 + **Qwen3.6-27B**（:8001，关思考）作
  规划/路由，MockBody 作本体。中英任务都产出正确的 node 绑定动词 plan、派发到 SUCCESS、speak
  语言匹配；问答带 node id 引用。**时延在 B2 预算内** —— 问答均值 0.41s（预算 0.1–0.5s），任务
  均值 0.75s（预算 0.5–2s）。eval harness 的引用指标暴露真实弱点：Cosmos 在部分英文问答上
  少引用（validity 0.5）—— 模型质量发现、非代码 bug。
- **▢** 云启动 → `base_url` 切 Thor（B6）—— 需硬件。

时延预算（B2）：查询 100–500 ms，简单任务 0.5–2 s。**已达标。**

**出口：** 生产推理器驱动全回路；评测阈值达标；云 → Thor 切换验证。

---

### P7 —— 边缘回退：本体离线 AI 链路  ·  ◐ (P7.1 完成)  ·  M-L3.5  ·  横切

**Spec：** [specs/P7-edge-fallback.md](specs/P7-edge-fallback.md)。网络断时靠本体保持认知可用
—— 小本地 LLM + 本体 ASR + TTS 构成自给链路。远端大模型为主；本体是**降级回退**，绝不丢失
安全与记忆（二者本就本地）。

- **P7.1 ✅** —— `FailoverVerbalizer`：包 `[远端, 本体]` Verbalizer；遇 `QueryError` 回落本地
  服务，基于调用计数滞回。复用 `Verbalizer` seam → 覆盖 Reasoner + Planner/IntentRouter，**大脑零改动**。
- **P7.2 ✅** —— `Listener`（ASR）+ `Speaker`（TTS）BYO seam + `Mock*` + 薄 `voice.py`
  `VoiceLoop`（听→想→说）。网络隔离。
- **P7.3 ▢** —— 接选定边缘栈（**Qwen 对齐**：Reasoner=Cosmos-Reason2，Planner=Qwen3.x-8B，
  ASR=Qwen3-ASR，TTS=Qwen3-TTS）于 Jetson Thor/Orin；验证。
- **P7.4 ▢** —— 降级契约 + 模式 telemetry + "我离线了" UX。

**未决 owner 决策（spec §7）：** 降级非对等（D-edge-1）；ASR/TTS 作新 BYO seam（D-edge-2）。
**边缘栈：已定 Qwen 对齐。**

---

## 4. 里程碑

| 里程碑 | 阶段 | 状态 | 完成定义 |
|---|---|---|---|
| **M-L3.1** | P1 | ✅ | instruction → 带引用动词 plan → MockBody 派发 |
| **M-L3.2** | P2 + P3 | ✅ | 技能卡跑通；每个 plan 经策略检查 |
| **M-L3.3** | P4 + P5 | ✅ | 完整 S2 回路带痕迹+重规划；端到端场景复现 |
| **M-L3.4** | P6 | ▢ | 真 Cosmos-Reason2 + 评测达标 + 云→Thor |
| **M-L3.5** | P7 | ◐ (P7.1 ✅) | 拔网 —— 机器人仍听到、规划、过 gate、动作、说话，全本体 |

---

## 5. 横切与依赖

- **L4 痕迹归属（P4）：** 建在 `mindloop`（`trace.py`），引用 node id。D2 设想并入 tempomem
  **核心**已**推迟** —— 见 §8。
- **本体团队请求（`body-team-asks-v0.md`）：** `/l2/capabilities`、世界系检测、node-id seam、
  类型化错误。**MockBody + Genesis 仿真当下解锁全部 L3** —— 真机集成等这些答复。
- **Episteme 检索 encoder（P2）：** BYO encoder（测试用 hash）；真 encoder 后置 extra 仍可选/未接。
- **命名（architecture §10）：** Psyche / Episteme / Phylax / Hexis —— **已采用**：`episteme.py`
  + `phylax.py` 作模块名发了（"先确认"闸视为已了；owner 想重议见 §8）。

## 6. 风险

| 风险 | 缓解 / 状态 |
|---|---|
| L4 痕迹 ↔ tempomem 核心耦合 | **以偏离解决** —— 建在 mindloop 引用 node id；核心合并推迟（§8），无核心发版卡 P4 |
| Episteme 检索质量 | 规则优先；语义检索增量（已发 BYO-encoder） |
| Cosmos-Reason2 时延 vs B2 预算 | 上 Thor 前 P6 评测测量 |
| 策略完备性（无 FMEA） | 从 B2R 硬约束枚举；**FMEA 仍 open**（§8） |
| 蔓延进 L2/L1 | 硬线 —— L3 开发本体只 MockBody/仿真 |

---

## 7. 排序

`P0 → P1 → (P2 ∥ P3) → P4 → P5 → P6`，**P7 横切**（P7.1 应 owner 请求提前落；P7.2–7.4 卡在
未决 §7-spec 决策）。D3 本体适配轨在 `bodylink` 并行。**P5 已关 M-L3.3**（首个全回路集成证明）；
**P6 是关键路径下一步**（真 reasoner + 评测）。

---

## 8. 未决项 & 决策日志

| 项 | 状态 | 备注 |
|---|---|---|
| **D2：L4 痕迹 → tempomem 核心合并** | 推迟（2026-06-28） | 建在 mindloop；核心合并是未来跨仓协调改动。别丢。 |
| **模块命名**（Episteme/Phylax/Hexis） | 已采用 | 未单独 owner 签字就作模块名发了；不合意可重议 |
| **Phylax FMEA** | open（继承） | 策略从 B2R 硬约束枚举，非失效模式分析所得 |
| **P6 评测阈值** | 已提议 | `EvalThresholds` 默认：规划 ≥0.9、策略 =1.0、重规划 ≥0.8、意图 ≥0.95 —— 待 owner 批准 |
| **negation_constraints SubTask 字段** | 未加 | P4 不需要；要 B2R 重规划完全对等再加 |
| **bodylink → 独立仓/子模块** | ✅ 完成（2026-06-29） | wikieden/bodylink（私有）+ root 子模块，同 mindloop/tempomem/worldsense |
| **voicelink 语音成员** | ✅ 完成（2026-06-29） | 第 6 成员：ASR/TTS 引擎填 `Listener`/`Speaker` seam（P7）；暂在 root |
| **D3 本体轨**（真 HW adapter、BT/反射 Phylax 层） | 待定 | bodylink 设计文档 + TECH-DESIGN 追踪，此处未分期 |
| **动态场景上下文**（主动感知） | ✅ 第 1–4 步完成 | seam + `WorldState` 回写 + 幂等派发 + 主动感知尾部重规划 —— 感知-行动-更新回路闭合；见 research/dynamic-scene-context.md |

---

*2026-06-28 更新。每阶段先写 spec；声称 done 前先验证。*
