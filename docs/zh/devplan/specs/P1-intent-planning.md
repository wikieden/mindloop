> 🌐 [English](../../../en/devplan/specs/P1-intent-planning.md) · **中文**

# P1 spec —— 意图路由 + 规划骨架（M-L3.1）

**状态：** 已批准（owner，2026-06-26）。实现 [DEV-PLAN.md](../DEV-PLAN.md) §P1。
**B2R 参考：** `l3/intent_router.py`、`l3/task_planner.py`、`l3/subtask_compiler.py`、
`shared/types.py`。推理结果格式**照搬 B2R MVP**（owner 指令）。

## 1. 采用的 B2R-MVP 格式

B2R MVP **两段式**规划：

```
LLM → CommandSequence{commands: list[str]}        # 紧凑文本动词行
      ["NAVIGATE counter", "GRASP mug", "SPEAK ok"]
            ↓ compile_to_subtasks()   纯函数、查表、零 LLM
      list[SubTask]{ type, target_id, skill, params,
                     preconditions, effects, timeout_s, ... }
```

LLM 只出**紧凑文本动词序列**（直观、省 token、schema 稳、不易幻觉）；**确定性
编译器**按动词查表填结构化字段（skill/preconditions/effects/timeout）。序列以
告知用户的话结尾。

## 1a. 控制流 —— LLM 决策、规则编译（规划链无规则回退）

分工是 **Stage 1 走 LLM、Stage 2 走规则**，**不是**"LLM 不行就回退到规则规划"。
线上规划**永远是 LLM**；规则层只是确定性**后处理**（填 schema + 安全 gate），
绝不当替补规划器。（B2R 的"LLM 不可用 → 硬编码序列"那条路径**未采用**——我们没有
预置 plan；LLM 空回复 = 空 plan，安全。）

```
                    instruction
                        │
              ┌─────────▼──────────┐
              │  IntentRouter      │  ◀── LLM   (VerbalizerIntentRouter)
              │  classify()        │      task / question / chat
              └───┬────────────┬───┘
        question/ │            │ task
          chat    │            │
        ┌─────────▼──┐   ┌─────▼──────────┐
        │ ask()      │   │  Planner       │ ◀── LLM   (VerbalizerPlanner)
        │ 检索→推理   │   │  plan()        │     出**文本**动词行
        │ (LLM)      │   └─────┬──────────┘     "navigate table / grasp mug / speak …"
        └─────┬──────┘         │
              │          ┌─────▼──────────────────────────┐
              │          │  compile_commands()            │ ◀── 规则（确定性）
              │          │  • _VERB_TABLE → skill/pre/eff │     零 LLM
              │          │  • mem.query → 绑 node id   B9  │
              │          │  • 丢弃本体不支持的动词     D3  │
              │          │  • 无 speak 则补 default_speak │
              │          └─────┬──────────────────────────┘
              │                │ SubTask[]
              │          ┌─────▼──────────┐
              │          │ executor       │  ◀── 本体 seam (MockBody / 真机)
              │          │ dispatch()     │
              │          └─────┬──────────┘
              ▼                ▼
           Answer          StatusUpdate[]   →   HandleResult
```

**要点：** Stage 1 = LLM（意图 + 动词序列）；Stage 2 = 规则（`compile_commands`，
纯函数）。整个栈里唯一的**非 LLM 退化**在 `tempomem.query`（没配 encoder 时
语义→关键词，BYO 契约）——**规划链没有任何退化**。`Scripted*` 类只是测试桩；线上
`Brain` 注入的是 `Verbalizer*`。

## 2. 三处 ratified 适配

| B2R MVP | mindloop P1 | 为何 |
|---|---|---|
| LLM → `CommandSequence` 文本行 | **照搬** | 省 token、稳 |
| `compile_to_subtasks()` 查表填 | **照搬** | 可靠、不靠 LLM 编元数据 |
| `type` 固定枚举（`KNOWN_VERBS`） | **开放词汇 `verb`**，查本体 `CapabilityManifest` 校验 | D3 —— 换本体加动词不改大脑 |
| `target_id: str`（`"mug"`） | 编译时 `mem.query` 绑**场景图 node id** | B9 —— `cited_node_ids` 审计链闭合 |
| L3 强制 `preconditions`/`effects` | **作 SubTask 元数据保留、大脑不强制**——交 `bodylink` 符号 BT 层 | D4 —— 大脑只管 S2，BT 校验是中间层 |

## 3. 类型

`execute.py` —— 扩 `SubTask`（向后兼容，新字段全默认值）：加
`skill`、`preconditions`、`effects`、`timeout_s`。大脑**携带但不强制**
preconditions/effects（D4 —— bodylink 的 BT 强制）。

`plan.py` —— 新模块：`Intent`（task/question/chat）、`Command`（解析后的 LLM
文本行）、`Plan`（subtasks + speak + rationale）、`HandleResult`、`IntentRouter`
+ `Planner` 协议、`Verbalizer*`（LLM 后端）+ `Scripted*`（网络无关测试）。

## 4. 编译器

`compile_commands(commands, mem, manifest) -> Plan`：纯（只读 mem 解 node id）。
每条 Command：`speak` → 进 `Plan.speak` 不下发；verb **不在 manifest** → **丢弃**
（D3，记日志）；否则查动词元数据表填 skill/preconditions/effects/timeout，每个
物体 arg 经 `mem.query` 绑 node id（B9）→ 出 `SubTask`。动词表对齐 B2R
`subtask_compiler`；manifest 支持但表里没有的动词 → 空元数据照样出（开放词汇 D3）。

## 5. Brain.handle

`Brain(mem, reasoner, *, router=None, planner=None, executor=None)`。
`handle(instruction)`：路由 → question/chat 走 `ask`；task → 规划 → 编译 →
（有 executor 则）逐 SubTask dispatch → 收终态。router/planner/executor 可选
（ask-only Brain 照常用）；未配 handle 抛 `BrainError`。

## 6. 测试（`tests/test_plan.py`，网络无关）

"拿桌上的瓶子" → ScriptedPlanner 出 navigate/grasp/speak → 编译 → 带 node id
的 SubTask + speak 入 Plan.speak + MockBody 下发终态 SUCCESS（node id 回带）；
manifest 外动词丢弃不下发；question → ask；编译绑 node id；未知物体 → 空 targets。

## 7. 文件

`execute.py`（扩 SubTask）· `plan.py`（新）· `brain.py`（加 `handle`）·
`errors.py`（`BrainError`）· `__init__.py`（导出）· `tests/test_plan.py`（新）·
`CHANGELOG.md`。

**出口（M-L3.1）：** 一条家务指令产出动词计划、下发 MockBody、每槽位带 node id；
不支持动词被拒。
