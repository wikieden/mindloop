> 🌐 [English](../../en/devplan/DEV-PLAN.md) · **中文**

# mindloop L3 大脑 —— 开发计划

**范围：** 把 L3 认知大脑（`mindloop`）从今天的问答回路，建设成已拍板决策
所描述的完整 S2 编排器。**L1/L2（执行、真机）暂缓 —— 其设计复用 Brain2Robot
既有的 L2/L1 工作**（owner，2026-06-15）。`bodylink` 的 `MockBody` 在整个 L3
开发期充当机身替身。

**依据：** 决策 D1–D5 + K1–K3（brain-architecture.md §9，2026-06-15 拍板）
与本体契约 B1–B10（§11，2026-06-11 拍板）。每个阶段**先查对应的 Brain2Robot
设计文档**（常驻指令 —— B2R 是原型产品）。

**状态：** 计划 v1，2026-06-15。每个阶段的 spec 获批前不写代码。

---

## 0. 原则（适用每个阶段）

- **只做 L3。** mindloop 拥有 S2（意图 → 规划 → 重规划 → 对话）+ Phylax 策略层
  + 协议缝。执行、符号 BT 安全、真机都不进（D1）—— 复用 B2R / 留给 `bodylink`。
- **大脑核心维持 stdlib-only。** 重依赖（LLM 客户端、编码器）藏在 extra 或外部
  端点后。与今天同契约。
- **网络无关测试。** 每个阶段对 `ScriptedReasoner` + `MockBody` + hash 编码器
  测试 —— 绝不用真 LLM 或模型下载。
- **接地 + 可审计。** 计划把物体槽位绑到场景图 node id；回答引用 node id；
  每个决定落 L4 痕迹。像素 → 执行器审计链不断（B9）。
- **先查 B2R。** 每个阶段标明它移植的 B2R 文档；除非被已拍板决策明确取代，
  否则收编其机制。
- **双语文档、Conventional Commits、每次改动更 CHANGELOG、CI 矩阵、
  ruff + pyright 门** —— 与 tempomem core 同一工程标准。

---

## 1. 现状（基线）

| 能力 | 状态 | 位置 |
|---|---|---|
| `Brain.ingest`（记忆） | ✅ 已交付 | `brain.py` |
| `Brain.ask`（检索 → 推理 → 带引用 Answer） | ✅ 已交付 | `brain.py` |
| `Reasoner` / `Verbalizer` 协议 + Scripted / Verbalizer / CosmosReason | ✅ 已交付 | `reason.py`、`verbalizers.py` |
| `ExecutorAdapter` 协议 + `SubTask` / `StatusUpdate` / `CapabilityManifest` + 类型化 `ErrorCode` / `RecoveryHint` | ✅ **P0 完成** | `execute.py` |
| `PreferenceStore`（L5）占位 + `HealthReport`（B5）+ `Brain.health()` | ✅ **P0 完成** | `preference.py`、`health.py`、`brain.py` |
| `MockBody` 参考执行器 + `bodylink` 包 | ✅ **P0 完成** | `bodylink/` |

P0 完成：执行缝（D1/D3）落在 `execute.py`（开放词汇动词、带 node id 的
`SubTask`（B9）、类型化 `ErrorCode`/`RecoveryHint`（B3）、双层
`CapabilityManifest`（D3）），`bodylink` 成员发布 `MockBody` 来填它。P0 以下
全部是**全新** L3 能力 —— **下一步 P1**。

---

## 2. 阶段图

```
P0 契约 ─► P1 意图+规划 ─► P2 Episteme ─► P3 Phylax ─► P4 痕迹+重规划 ─► P5 全回路 ─► P6 生产化
  (缝)       (S2 脊椎)      (技能)         (策略)        (记忆+修复)        (对话)        (真 LLM+评测)
```

| 阶段 | 主题 | 里程碑 |
|---|---|---|
| P0 | 缝契约 + 测试脚手架 | —（基本完成） |
| P1 | 意图路由 + 规划骨架 | **M-L3.1** |
| P2 | Episteme 技能卡库 | **M-L3.2** |
| P3 | Phylax 策略层 | M-L3.2 |
| P4 | L4 痕迹 + 重规划 | **M-L3.3** |
| P5 | 对话 + 完整 S2 回路 | M-L3.3 |
| P6 | 生产推理器 + 评测 + 云启动 | **M-L3.4** |

---

## 3. 各阶段

### P0 —— 缝契约 & 测试脚手架  ·  ✅ 完成（2026-06-16）

**目标：** 冻结 L3 规划所依赖的协议，使 P1+ 是纯大脑逻辑。

- ✅ `ExecutorAdapter` 协议 + 值类型（`SubTask`、`StatusUpdate`、
  `CapabilityManifest`/`BodyProfile`/`VerbSpec`、`TaskStatus`/`ErrorCode`/
  `RecoveryKind`/`RecoveryHint`）—— `execute.py`。开放词汇动词（D3）、node id
  携带 + 回带（B9）、类型化错误/恢复（B3）、双层清单（D3）。
- ✅ `PreferenceStore` 协议占位（L5，D2）—— `preference.py`，临时。
- ✅ `HealthReport` + `Brain.health()`（B5）—— `health.py`、`brain.py`。
- ✅ `bodylink` workspace 成员已建（D5 第 4 包）+ 注册进根 `pyproject.toml`
  （`[tool.uv.workspace]` + `[tool.uv.sources]`）。`MockBody` 参考
  `ExecutorAdapter` + `g1d_manifest()`（B10）+ `UnsupportedVerbError`。
  在 workspace 里 build+install（`uv sync`）。
- ✅ 契约测试：`mindloop/tests/test_execute.py`（缝值类型）+
  `bodylink/tests/test_mock_body.py`（dispatch 往返、node id 回带、类型化失败
  恢复、runtime-checkable 符合性、动词门控）。

> `bodylink` 暂为 **workspace 内目录**（根仓），尚未像另三个那样独立 GitHub
> 仓/submodule。发布前毕业为独立仓（需 owner 放行 —— 建仓是外向动作）。
> 在此标注以免遗漏。

**B2R 参考：** `code_framework.md`、`system_integration.md`、
`embodiment_adaptation.md`（Body Profile 层）。
**测试：** 缝值类型契约 + MockBody dispatch 往返 —— 完成。
**验证：** 本地 **189 passed, 2 skipped · ruff clean · pyright 0**（tempomem +
mindloop + worldsense + bodylink）。RTX PRO 交叉验证待办（P0 收尾时主机离线；
此前已验证为可用 dev 环境，176 测试）。
**出口：** 所有缝协议冻结 ✅；`bodylink` build+install ✅；node-id + 类型化
错误契约锁定 ✅。

### P1 —— 意图路由 + 规划骨架  ·  ✅ 完成（2026-06-26）  ·  M-L3.1

**Spec：** [specs/P1-intent-planning.md](specs/P1-intent-planning.md)（B2R-MVP
两段式格式）。**目标：** 把 `Brain` 从问答盒变成路由器 + 规划器。

- `IntentRouter` —— 把指令分类为 `{任务, 提问, 闲聊}`。
- `Planner` —— 任务意图 → **技能动词**的 `list[SubTask]`；查本体的
  `CapabilityManifest`，**本体不会的动词绝不下发**（D3）。
- `Brain.handle(instruction)` —— 编排：路由 → (`ask` | 规划+下发 | 闲聊)；
  把物体槽位绑到 node id（B9）。

**B2R 参考：** `l3/intent_router.py`、`l3/task_planner.py`、`psyche_layer.md`。
**测试（ScriptedReasoner + MockBody）：** "拿桌上的瓶子" → `[navigate, pick]`
计划，所有槽位带引用；不支持的动词 → 拒绝、不下发。
**出口：** 一条家务指令产出动词计划，下发到 MockBody，每个物体槽位都带
node id。✅ 达成 —— `plan.py` + `Brain.handle`；8 个网络无关测试；全套 197 passed；
ruff clean；pyright 0。并对真 Cosmos-Reason2 vLLM 端点端到端交叉验证（意图路由 +
LLM 动词计划 → node 绑定下发 + 带引用问答）。

### P2 —— Episteme 技能卡库  ·  M-L3.2  ·  D3/§5、K2  ·  ✅ DONE

**目标：** 程序性知识做成数据 —— 做菜 / 按面料洗衣。
**已完成（2026-06-28）：** `episteme.py` —— 见 [specs/P2-episteme-skill-cards.md](specs/P2-episteme-skill-cards.md)。

- `SkillCard` schema —— **flat steps + rules（K2）**；DAG 留 schema 版本位。
  字段：`id`、`category`、`preconditions`、`rules`、`steps`、`failure_hints`、
  `safety`、`provenance`。
- YAML 卡加载器 + 卡库**语义检索**。
- 实例化：绑 category → node id、解规则、叠加 L5 偏好、查清单 → 展开动词序列。
- 无卡 → LLM 通用知识兜底，标低置信。

**B2R 参考：** `techne_crystallization.md`、`household_task_taxonomy.md`、
`appliance_interaction.md`。
**测试：** `laundry_basic` + 一张做菜卡 → 动词计划；羊毛/深色规则解析为正确
程序；缺卡兜底标记。
**出口：** 洗衣 + 做菜卡对 MockBody 端到端跑通。

### P3 —— Phylax 策略层  ·  M-L3.2  ·  D4 顶层（语义）

**目标：** 可移植的大脑侧安全层（另两层 Phylax —— `bodylink` 的符号 BT、
固件的反射 —— 暂缓）。

- 声明式策略配置：禁区、人距限速、动作白名单、按角色权限门控。
- 规划 → 下发之间的策略检查门；每个计划下发前必过。
- 安全类处置：停 + 语音，**不绕行、不重试**。
- 社区技能卡不可信：带 `safety:` 标注的卡须经签名 + 审核门才生效。

**B2R 参考：** `safety_architecture.md`（移植 §2 L3 硬约束、§8 权限、§9 仲裁；
**"上层的想做不能覆盖下层的不可以"**）。
**测试：** 非成人发起刀具 → 拒绝；人旁超速 → 拒绝；未签名 `safety:` 卡 → 拒绝。
**出口：** 每个下发计划都过了策略检查；违规被拦 + 入痕迹。

### P4 —— L4 痕迹 + 重规划  ·  M-L3.3  ·  D2 + B3

**目标：** episodic 记忆 + 失败驱动修复。

- **L4 痕迹存进 tempomem core**（D2）—— episodic：计划、结果、策略决定；
  每条引用场景 node id（共享 id 空间）。*跨仓：需 tempomem core 改动 ——
  与 core changelog 协调。*
- `Replanner` —— 失败 `StatusUpdate`（类型化 `ERR_*`，B3）→ 用技能卡的
  `failure_hints` + 类型化调整词汇（`position_offset`、`orientation_relax`、
  `force_adjustment`）重规划。

**B2R 参考：** `trace_memory.md`、`L3_cognition.md` 的否定性重规划回路。
**测试：** 抓取失败 → 带调整重规划；L4 痕迹记录两次尝试，按 node id 可查。
**出口：** 失败下发触发有界重规划；L4 痕迹可查、带引用。

### P5 —— 对话 + 完整 S2 回路  ·  M-L3.3

**目标：** 完整认知回路，对 MockBody 端到端。

- 对话引擎 —— 记忆接地闲聊（扩展 `ask`）；多轮上下文。
- 全回路接通：指令 → 路由 → 规划 → 策略 → 下发 → 状态 → 重规划 → 痕迹。
- L5 `PreferenceStore` 叠加 —— 偏好按人改写卡默认值。

**B2R 参考：** `05_scenarios/breakfast_e2e.md`、`e2e_walkthrough.md`。
**测试：** 对 MockBody 复现 B2R 早餐 / 清理场景 —— 全程带引用、入痕迹、无真网络。
**出口：** 一个 B2R 端到端家务场景在完整 S2 回路 + MockBody 上跑通。

### P6 —— 生产推理器 + 评测 + 云启动  ·  M-L3.4  ·  B6

**目标：** 把 ScriptedReasoner 换成真 LLM；测量；部署。

- 把 `CosmosReasonVerbalizer`（已有）接成端到端 S2 推理器。
- 评测 harness：规划准确率、引用合规、策略合规、重规划成功率（扩展 tempomem
  `bench` + brain `eval`）。
- 云启动 → `base_url` 一切落 Thor 本体（B6），协议零改动。

**B2R 参考：** `roadmap_techstack.md`、`mvp_plans.md`。
**测试：** 真 Cosmos-Reason2 跑回路；评测套对预算达标（B2：查询 100–500 ms，
简单任务 0.5–2 s）。
**出口：** 生产推理器驱动全回路；评测阈值达标；云 → Thor 切换验证。

---

## 4. 里程碑

| 里程碑 | 阶段 | 完成定义 |
|---|---|---|
| **M-L3.1** | P1 | 指令 → 带引用动词计划 → MockBody 下发 |
| **M-L3.2** | P2 + P3 | 技能卡跑通；每个计划过策略检查 |
| **M-L3.3** | P4 + P5 | 完整 S2 回路带痕迹 + 重规划；复现 B2R 场景 |
| **M-L3.4** | P6 | 真 Cosmos-Reason2 + 评测绿 + 云→Thor |

---

## 5. 横切 & 依赖

- **tempomem core 改动（P4）：** L4 痕迹存落在 core，不在 mindloop —— 经 core
  CHANGELOG 协调；保持 numpy-only 契约。
- **本体团队需求（`body-team-asks-v0.md`）：** `/l2/capabilities`、世界系检测、
  node-id 缝、类型化错误。**MockBody 期间解锁全部 L3** —— 真机集成等这些答复。
- **Episteme 检索的编码器（P2）：** 语义卡检索需编码器；测试用 hash 编码器，
  真编码器藏 extra 后。
- **命名（架构 §10）：** Psyche / Episteme / Phylax / Hexis —— 成为公开模块名
  前确认。

## 6. 风险

| 风险 | 缓解 |
|---|---|
| L4 痕迹耦合 mindloop ↔ tempomem core | 先把 L4 落 core（P4 卡在一次 core 发布上） |
| Episteme 检索质量 | 先规则优先；语义检索增量叠加 |
| Cosmos-Reason2 延迟 vs B2 预算 | 云启动；P6 评测先测量再落 Thor |
| 策略完整性（暂无 FMEA） | 从 B2R 硬约束枚举；FMEA 是继承的待决项 |
| 范围蔓延进 L2/L1 | 硬线 —— 暂缓、复用 B2R；L3 开发期唯一机身是 MockBody |

---

## 7. 排期

P0 → **P1** → (P2 ∥ P3) → P4 → P5 → P6。P1 落地后 P2、P3 可并行（卡需要规划器；
策略包住规划器 —— 互相独立）。P4 的 L4-进-core 依赖是唯一跨仓门 —— 尽早启动
core 改动。

*计划 v1，2026-06-15。每个阶段先 spec 再码；声明完成前先验证。*
