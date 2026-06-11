> 🌐 [English](../en/brain-architecture.md) · **中文**

# 大脑架构 —— 三层认知栈

**状态：** 提案 v1（头脑风暴产出，2026-06-11）。本文是 Brain2Robot 正式化
（开源、多设备）并**重构进本包**的决策记录。决策 D1–D5 与三个设计旋钮（§9）
为推荐项，**待拍板** —— 拍板前不实现任何内容。§11 本体契约规则（B1–B10）
**已拍板**（owner，2026-06-11）。
**读者：** 参与生产版大脑的贡献者；移植新机器人本体的集成者。
**配套文档：** [cosmos3-tempomem-llm-brain.md](cosmos3-tempomem-llm-brain.md)
（本栈所包裹的记忆↔推理内环）、[local-serving.md](local-serving.md)
（自托管推理器）、[post-training-rl-roadmap.md](post-training-rl-roadmap.md)
（哪些模型做 SFT/RL）。

## 1. 主张

家用机器人大脑不是一个模型 —— 是**三个不同速度的回路**，各自放在延迟预算
允许的位置：

| 层 | 速度 | 职责 | 载体 | 部署 |
|---|---|---|---|---|
| **慢思考 Deliberation**（S2，"Psyche"） | 慢，~秒级 | 意图→规划→重规划→对话；记忆接地推理 | LLM/VLM（BYO，OpenAI 兼容） | 云启动 → `base_url` 一切落 Thor 本体，协议零改动 |
| **习惯 Habit**（S1） | 中，~100 ms | 技能执行：技能卡实例化为技能动词行为树；监控；上报 | BT runtime + 记忆查询（numpy core 本地） | **本体固定** |
| **反射 Reflex** | 快，~1 ms | 急停、力矩限幅、碰撞反应 | 设备固件 / 实时控制器 | **本体固定；按本体** |

brain 包只拥有慢思考层和另外两层要填的**契约**。Habit 的参考运行时与所有
本体都在协议缝之外（§3）。Reflex 对大脑是黑盒：只读状态，永不驱动。

当前算力：**Jetson AGX Thor** = 本体，**RTX PRO 6000（96 GB）** =
开发/训练（LoRA、评测），云 = 仅启动期。

## 2. 三层详解

### 2.1 慢思考（S2）—— 本包的本体

在已交付的认知回路上扩展出规划：

```
用户/世界事件
  → 意图路由（任务? 提问? 闲聊?）
  → 检索：SpatialMemory.query(k) → serialize(node_ids=hits)   # 带引用的上下文
  → 推理：Reasoner (LLM) → 技能动词计划，或 Answer(text, cited_node_ids)
  → 策略检查（Phylax，§6）→ 经 ExecutorAdapter 下发给 Habit
  → 收到失败上报 → 重规划（用技能卡的 failure hints，§5）
```

S2 的一切输出都**接地**：计划把物体槽位绑到场景图 node id；回答引用
node id。从相机像素到执行器指令的审计链不断。

从 Brain2Robot（实验仓）收编：意图路由、任务规划、重规划、对话引擎 ——
全部改写到 `SpatialMemory` 之上，替换 B2R 手写的 scene graph / WorldState。

### 2.2 习惯（S1）—— 在执行缝之外

技能卡实例化产出**技能动词**行为树计划（§4）。参考 BT 运行时、mock 本体、
仿真器放独立 workspace 成员（`tempomem-exec`，提案，§3）；真机
（如 Unitree G1）是独立包，实现同一个 `ExecutorAdapter`。

### 2.3 反射 —— 刻意出界

按本体、不可协商、本体固定。大脑对它的唯一接口是状态摄取（入痕迹、供
重规划）和配置*读取*。任何大脑代码路径都不能放松反射限幅。

## 3. 包边界（D1、D5）

```
tempomem            core：场景图记忆（L3）+ 痕迹（L4，提案）    numpy-only
worldsense 眼睛：RGB-D → 世界系 Detections             [clip] extra
mindloop      本包：S2 + Episteme 技能卡 + 协议缝          stdlib core
tempomem-exec       提案：ExecutorAdapter 参考实现（BT + MockBody，Genesis 进 [sim]）
```

brain 核心维持 stdlib-only，与今天一致。它发布**协议**，别人发布实现 ——
和记忆核心 `PerceptionAdapter` / `Verbalizer` 同一手法：

| 缝 | 协议（住本包） | 谁来填 |
|---|---|---|
| 执行 | `ExecutorAdapter` —— 下发计划、流式状态、暴露能力清单 | `tempomem-exec`、设备包 |
| 推理 | `Reasoner` / `Verbalizer`（已有） | 任意 OpenAI 兼容端点 |
| 偏好 | `PreferenceStore`（L5，提案） | 外部实现（Mem0 等） |

**不**进本包的东西：py-trees、Genesis/Isaac、ROS2/Redis 传输、场景资产 ——
B2R 的 L2/L1/sim/transport 留在缝外。

## 4. 动作接口：技能动词 + 能力清单（D3）

7-DOF-EE + 夹爪的 canonical 动作空间**直接废弃，不修**。大脑用**技能动词**
规划（`navigate`、`pick`、`place`、`open`、`operate_appliance`……）；每个
设备发布**能力清单（capability manifest）** —— 支持哪些动词、参数域、家电
类型。规划时查清单：本体不会的动词 → 降级或拒绝，绝不下发。

多设备支持 = 多份清单，不是新几何。双臂、全身、移动 = 多几个动词。
关节空间归一化是 L1/L2 的问题，大脑拒绝接手。

## 5. Episteme —— 生活技能知识层

程序性知识（做菜技巧、按面料定洗衣方案）做成**数据，不做代码，不烧权重**：
声明式**技能卡**。

```yaml
id: laundry_basic_v1
category: laundry
preconditions: {appliances: [washer], verbs: [pick, place, operate_appliance]}
rules:                                  # 判断知识
  - if: {fabric: wool}                  → {program: wool, temp: 30, spin: low}
  - if: {color: dark, first_wash: true} → {batch: separate}
steps:                                  # 程序知识 —— 只引用类别，绝不引用实例 id
  - sort(clothes, by: rules)
  - load(washer, batch)
  - operate_appliance(washer, program)
failure_hints: [door_blocked → retry_after(open_door)]
safety: [chemicals]                     # Phylax 钩子，明火/刀具/化学品卡必填
provenance: builtin | community | distilled | user_taught
```

卡只引用**类别与 affordance**；绑定到真实场景图节点推迟到规划时
（带 `cited_node_ids`）。这就是卡能跨家庭、跨本体移植的原因。

运行时：意图 → 对卡库做语义检索（无卡 → LLM 通用知识兜底，标低置信）→
S2 实例化：绑节点、解规则、叠加 L5 偏好、查能力清单 → 展开为动词 →
执行 → 轨迹入 L4。

**可扩展阶梯**（开源增长引擎）：
1. 加一个卡文件 —— 零代码；
2. **技能包**（版本化集合，声明依赖的动词集 + 家电类型）—— 社区分发；
3. **结晶**：L4 痕迹里反复成功的 LLM 兜底方案 / 用户纠正 → LLM 起草新卡 →
   人审 → 入库；
4. LoRA 蒸馏 —— 只给高频且卡表达不了的技能；最后手段，在 RTX 机上做。

属性供给：面料/颜色/状态来自感知 Route D（VLM 语义富化 → node
`attributes`）—— 洗衣规则就是该字段的第一个真实消费者。

## 6. 安全 —— Phylax 两层（D4）

| 层 | 内容 | 位置 | 可移植? |
|---|---|---|---|
| **策略**（语义） | 禁区、人距规则、动作白名单；每个计划下发前过一遍声明式策略检查 | S2 与执行缝之间 | 是 —— 配置文件，随 brain 发布 |
| **反射**（物理） | 急停、力矩/速度限幅、碰撞 | 设备固件 | 否 —— 按本体；大脑只读状态 |

每个策略决定、每个下发的计划连同触及的 node id 一起落 L4 痕迹 —— 审计
端到端闭合。社区技能卡是不可信输入：带 `safety:` 标注的卡须经签名 +
审核门才生效。

## 7. 记忆（D2）

| 层 | 内容 | 位置 |
|---|---|---|
| L3 场景图 | 物体、区域、关系、向量 | `tempomem` core（已交付） |
| L4 痕迹（episodic） | 计划、结果、策略决定 | **进 core**（提案）—— 痕迹引用场景 node id；共享 id 空间的东西不该跨库 |
| L5 偏好 | 按人的口味、习惯、覆盖项 | **不进** —— `PreferenceStore` 协议；生命周期、隐私、按人隔离都不同 |

写入通道天然单写者：感知写 detections（走融合仲裁器），大脑写语义更新
（走 `update()`），不需要新仲裁机制。

## 8. 感知接口（消费方，不拥有）

双速率融合，融合点唯一（core 的仲裁器）：

- **Route A** 快环（10–30 Hz，本体固定）：开放词汇检测 + CLIP crop 向量 +
  depth lift → `Detection`。视频跟踪（`track_id` 写 `Detection.aux`）作
  关联先验 —— 旋钮 K1。
- **Route D** 慢环（0.1–1 Hz 关键帧，云 → Thor）：VLM → 结构化 JSON
  （状态/属性/affordance）。用 **Set-of-Marks** grounding：把已有 node 的
  bbox 投影回关键帧标 `#id`，VLM 直接用 node id 作答 —— 无模糊重关联，
  与 `cited_node_ids` 同一套 id 语言。

去重 = 仲裁器四信号打分（距离 + 3D-IoU + 向量 cos + 标签投票）+ 事后
`consolidate()` + `resplit()`。已跟踪的生产化缺口：同类相邻实例（K1 跟踪
缓解）、物体被挪后的幽灵节点（需视锥负证据；其余由 Route D "`#id`
moved" 兜底）。

## 9. 待拍板决策

| # | 决策 | 推荐 |
|---|---|---|
| D1 | 执行层 scoping | brain 只做 S2；执行走 `ExecutorAdapter`；L2/L1/sim/transport 不进 |
| D2 | 记忆统一度 | L3 + L4 进 core；L5 走外部协议 |
| D3 | 动作空间 | 技能动词 + 能力清单；废弃 7+1 canonical 空间 |
| D4 | 安全 | Phylax 两层：可移植策略层 + 按本体反射层 |
| D5 | workspace 形状 | 4 成员（`core / perception / brain / exec`）；真机出树；总命名延后 |
| K1 | track-before-fuse | 是 —— SAM2/ByteTrack `track_id` 进 `Detection.aux`，仲裁器作先验 |
| K2 | 技能卡格式 v1 | flat steps + rules；DAG 留 schema 版本位 |
| K3 | 结晶入库门 | 永远人审后才入库 |

## 10. 命名（按 B2R 规范：哲学词主名，工程名副标题）

候选，待 owner 确认：**Psyche** = 慢思考层（B2R 沿用）、**Episteme** =
技能卡库（源自 B2R 技能织网设计）、**Phylax** = 安全（沿用）、**Hexis**
（亚里士多德，ἕξις "习得的品性"）= 习惯层。Soma 留给本体/执行侧。

## 11. 本体契约对齐 —— G1-D 轮式人形（已拍板 2026-06-11）

第一个本体团队（G1-D：轮式底盘 + 双 6-DOF 臂 + 灵巧手，32 DOF，
Jetson AGX Orin）交付了 L2/L1 设计并对 L3 提出要求。其 L3↔L2 契约与本
架构独立收敛：子任务词汇 ≈ 技能动词（D3）；关节空间严格停在 L2 以下；
L1 硬件安全（双通道急停、安全 PLC、STO/SS1/SLS）正是反射层（D4）；其
错误上抬机制（L2 自愈 IK/导航，`ERR_GRASP_FAILED`/`ERR_OBJECT_LOST` 升
L3）就是重规划回路；其"世界模型"槽位（语义地图 + 物体状态跟踪，查询预算
100–500 ms）就是 Chronotope。其 ROS 2 接口收编为 **ExecutorAdapter
wire binding v0**。

Owner 裁定（2026-06-11）：

| # | 规则 |
|---|---|
| B1 | **VLA 快速路径不归大脑管。** 本体侧"VLA 模块"（规则引擎 + 模板匹配，<10 ms —— 不是 VLA policy 模型）在大脑*上游*分发：VLA 命中 → 直达 L2；未命中 → 大脑 S2。大脑不拥有、不维护 VLA 模板库；Episteme 仍是大脑自己的知识层。<100 ms 快速路径要求因此不约束大脑。 |
| B2 | 延迟契约照单接受：简单任务 0.5–2 s，复杂 2–10 s，世界模型查询 100–500 ms（Chronotope 远低于预算）。 |
| B3 | `error_code` + `recovery_actions` 标准化进 ExecutorAdapter 契约：类型化 `ERR_*` 枚举 + 类型化调整词汇（`position_offset`、`orientation_relax`、`force_adjustment` ……）—— 绝不用自由文本。 |
| B4 | 充电/电池任务 = 一张内置 Episteme 卡；零新机制。 |
| B5 | 大脑提供 health-check 接口，对应其 L3 初始化清单（`llm_model` / `world_model` / `task_library`）。 |
| B6 | 算力：S2 本体运行**仅限 Thor**。凡非 Thor 本体（含 G1-D 的 Orin）S2 一律上云 —— `base_url` 一切，协议零改动。 |
| B7 | Redis：按本设计、不按其设计 —— 大脑核心保持 transport 无关；缝绑定用原生 ROS 2 Service/Topic，无 Redis 依赖。 |
| B8 | 坐标系：进记忆的一律**世界系**（右手系，米）。基座系 ↔ 世界系转换归 L2。 |
| B9 | id 空间：大脑下发的子任务携带记忆 **node id**；L2 反馈原样回带。字符串别名（`bottle_1`）不过缝 —— `cited_node_ids` 审计链保持闭合。 |
| B10 | 能力清单：G1-D 即第一份 manifest 实例（动词：`navigate` / `grasp` / `place` / `detect` / `open_door` / `charging` ……；2D 底盘，无步行动词）。由本体团队暴露 —— 提案：`/l2/capabilities` service（其 spec 中缺失）。 |

Wire binding v0（缝 ↔ 其命名）：

| ExecutorAdapter | G1-D ROS 2 |
|---|---|
| 任务入口（进大脑） | `/l3/task_execute`（`TaskExecute.srv`）—— 由设备包里大脑的 ROS 壳承接，不在 brain core |
| `dispatch(subtask)` | `/l2/execute_subtask`（Service） |
| 状态流 | `/l2/task_status`（`TaskStatus.msg`：`task_id` / `subtask_id` / `status` / `progress` / `error_code` / `recovery_actions`） |
| 能力清单 | `/l2/capabilities`（提案，B10） |
| 检测 → 记忆 | `/detection/objects`（`DetectionArray`，5–15 Hz）→ `add_detections()` |
