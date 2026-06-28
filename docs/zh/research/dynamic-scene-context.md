> 🌐 [English](../../en/research/dynamic-scene-context.md) · **中文**

# 动态场景上下文 + 语义地图结合（设计）

**状态：** 设计（2026-06-28）。定义 seam + 感知-行动-更新回路；**尚未实现**（仅接口骨架 ——
§6）。配套 [l3-l2-fusion-roadmap.md](l3-l2-fusion-roadmap.md)。

LLM 当前怎么拿场景（静态、一次性），如何做成动态（执行中重查活地图），以及 tempomem 语义地图
如何作为枢纽让两者成立。

---

## 1. 现状 —— 静态、每次调用一次性

**写路径（地图更新，调用方驱动）。** `Brain.observe(rgb, depth, pose)`（`brain.py:88`）→
`mem.add_frame`(暂存) → `mem.commit()`（fuse-arbiter：去重/合并/更新位姿）→ `.smem` 场景图。
或 `Brain.ingest(detections)`（`brain.py:105`）。**只在调用方喂帧时更新地图。**

**读路径（上下文注入，每次推理冻结）。** 在 `ask`（`brain.py:110`）和 `_plan_context`
（`brain.py:296`）内：

```
mem.query(text, k)            # 路由：关系边 → 语义向量 → 关键词
   → top-k node_ids
mem.serialize(format="prompt", node_ids=…, max_tokens=budget)
   → 子图串：命中 + 其 1-hop 关系 + 层级祖先，token 预算裁剪（无命中则回退全图）
   → context  ──►  reasoner.reason(q, context) / planner.plan(instr, context)
```

**为何「静态」：** context 在 **`handle()` 起点 serialize 一次**。多步任务从那个快照**只规划
一次**；机器人移动、世界变化时，context **不刷新**、plan 不重接地。`brain.py` 明说：*"Active
perception (LLM → re-look) is future work."* 本设计就是这件未来工作。

---

## 2. 动态设计 —— 地图为唯一真相

tempomem 地图**本就动态存储** —— `query` 路由、`serialize` 子图、维护算子（`decay`、`forget`、
`consolidate`、`resplit`、`relate`、`define_region`、`update`）。缺口纯粹是**推理时的重注入
回路**：在对的时机重查活地图。「动态上下文」不是新存储 —— 是*何时*重 serialize。

### 2a. 三个源保鲜地图

1. **感知重看（眼）。** 执行中 —— 位姿变、失败、或显式请求 —— 重感知：`observe` → fuse →
   `map v#++`。
2. **效果回写（符号，无相机）。** SubTask SUCCESS → 把 `effects`（`robot.holding=apple`、
   `apple.location=trash`）写回地图。便宜、不开相机就闭环。（现在 effects 携带但不应用 —— D4；
   这步接上应用。）
3. **衰减/遗忘（时间）。** 没看见的物体 decay；`consolidate` 老化地图。已有。

### 2b. 重注入触发（何时给 LLM 重 serialize）

**不是**每步都建新 context —— 只在 focus 真动时：

1. **新指令**（现状）；
2. **派发失败** → P4 重规划重查新 context；
3. **效果回写或新感知触到 plan 依赖的节点**（*focus* 集）→ 前置条件复检 → 重审/重规划尾部；
4. **reasoner 主动要求重看**（active perception）。

### 2c. 回路

```
        ┌───────────────────────── tempomem 语义地图 (v#) ──────────────────────────┐
        │  物体 · 关系(on/in/near) · 区域 · 向量 · 情节(L4 痕迹)                       │
        └───▲────────────▲───────────────▲──────────────────────────────┬───────────┘
            │            │               │                              │ query(focus)+serialize
   ③ decay  │   ② 效果   │ 回写          │ ① 重看 (observe→fuse)          ▼  → context@v
   (时间)   │   (SUCCESS)│               │                       ┌──────────────────┐
            │            │               │                       │ reasoner/planner │ LLM
            │            │               │                       └────────┬─────────┘
            │            │               │                                │ plan / answer
            │      ┌─────┴─────┐   ┌──────┴───────┐                        ▼
            │      │  应用      │   │ 主动感知      │                ┌──────────────┐
            │      │  effects  │   │ active        │                │ dispatch     │
            │      └─────▲─────┘   └──────▲───────┘                │ subtask      │
            │            │ success        │ 步间                    └──────┬───────┘
            │            │                │                               │ StatusUpdate
            │      ┌─────┴────────────────┴───────┐   失败 (P4)            ▼
            └──────┤  StatusUpdate (类型化 + ids)   ├───► 重规划：重查新 context
                   └───────────────────────────────┘
   只在 focus 处的 v# 变化时才重 serve context（版本门控缓存）。
```

闭环：`map → context → LLM → plan → dispatch → status → {effects | replan | re-look} → map`。
效果回写让多步任务**不必每步开相机**就保持接地 —— 只在符号预测不确定时才真重看。

---

## 3. 语义地图应用

| 维度 | tempomem 已有 | 动态用法 |
|---|---|---|
| **空间-语义检索** | `query` 路由（关系/向量/关键词） | focus = 与*下一动作*相关的子图，非全图 |
| **区域/zone** | `define_region` | context 带机器人当前 region + 目标 region → 导航 + P3 禁区 |
| **关系作 grounding** | on/in/near 边 | 解析"桌上那个"；边被效果回写更新 |
| **情节/时序** | L4 痕迹(P4) + decay | context 可带"最后看见"recency；痕迹解释节点状态*为何*如此 |
| **affordance**（未来） | 节点带技能提示 | planner 读可供性选动词 |

---

## 4. focus + 版本门控（效率旋钮）

- **focus(turn)** = query 词（指令/问题）∪ plan 目标 `node_ids` ∪ 机器人当前 region。
- **地图版本 `v#`** 在每次 `commit` 和每次效果回写时 ++。
- context 按 `(focus, v#)` 缓存；**只在 `v#` 变化与 focus 相交时重 serialize**。所以远处物体
  移动不强制重规划，而你正要抓的杯子消失了会。

---

## 5. 接入点走查（`brain.py`）

| 位置 | 现状 | 加 |
|---|---|---|
| `ask`（`:110`）、`_plan_context`（`:296`） | 内联 `query`+`serialize` | 调 `SceneContextProvider`（抽出的 seam）返回 `(context, version)` |
| `observe`/`ingest`（`:88`/`:105`） | 调用方驱动写地图 | 也能被 `ActivePerception` 执行中调用 |
| `_dispatch_plan`（`:243`） | 每子任务派发一次 | 步间：SUCCESS 时效果回写；focus 陈旧检查；重看策略 |
| `_repair`（`:270`） | 从类型化失败重规划 | 重规划**重查新 context**（非陈旧的 plan 时上下文） |
| `handle`（`:163`） | 顶部一个 context | 顶部 context 是 `v0`；回路按触发重 serve |

---

## 6. seam 接口骨架（不实现 —— 先定）

```python
# scene_context.py —— 把读路径从 brain.py 抽出（先做到行为一致）
class SceneContextProvider(Protocol):
    def context(
        self, focus: Focus, *, max_tokens: int
    ) -> tuple[str, int]:                      # (序列化子图, 地图版本)
        ...

@dataclass(frozen=True)
class Focus:
    query: str                                 # 指令 / 问题
    node_ids: tuple[int, ...] = ()             # 要保持在视野里的 plan 目标
    region: str | None = None                  # 机器人当前 region

# effect_apply.py —— 闭符号回路（D4 携带 → 应用）
class EffectApplier(Protocol):
    def apply(self, effects: tuple[str, ...]) -> int:   # 返回新地图 v#
        ...

# active_perception.py —— 执行中何时重看
class ActivePerception(Protocol):
    def should_relook(
        self, *, last_status: StatusUpdate, focus: Focus, map_version: int
    ) -> bool:
        ...
```

首版**行为保持**：`DefaultSceneContextProvider` 原样包今天的 `query`+`serialize`；
`EffectApplier`/`ActivePerception` 默认 no-op。再逐个开关打开。

---

## 7. 分期

1. **抽出** `SceneContextProvider`（从 `ask`/`_plan_context`）—— 行为不变，只多 seam + `version`。
   **✅ 已完成（2026-06-28）** —— `scene_context.py`；`Brain(context_provider=…)`，
   `observe`/`ingest` 时 version ++。
2. **效果回写** —— SUCCESS 时把确认的 `effects` 应用到地图；对更新后的地图复检 plan 尾部前置条件。
3. **版本门控重 serialize** —— 重规划时 + focus 触及的 `v#` 变化时重查新 context。
4. **主动感知** —— 步间/不确定时的 `observe` 钩子；reasoner 可请求重看。

每步独立可发、网络隔离可测（脚本感知 + mock 地图版本）。
