> 🌐 [English](../../../en/devplan/specs/P4-trace-replanning.md) · **中文**

# P4 spec —— L4 痕迹 + 失败驱动重规划（M-L3.3）

**状态：** 已实现（2026-06-28）。实现 [DEV-PLAN.md](../DEV-PLAN.md) §P4。
**B2R 参考：** `l3/replanner.py`、`memory/trace_memory.py`、`trace_memory.md`、
`L3_cognition.md` 的否定性重规划回路。

## 1. 思想 —— 从失败学习、有界

派发的 `SubTask` 带类型 `ErrorCode` + `RecoveryHint`（B3）返回 `FAILED` 时，大脑去修复而非
盲目放弃 —— 但修复**有界且单向**：几次调整重试，然后停下问用户。每次尝试写入只增的 **L4
痕迹**（否定性学习燃料）。两个新件，均 stdlib + 无网络：

```
派发 SubTask ─► StatusUpdate
   │ SUCCESS ─► 下一步
   │ FAILED（类型 ErrorCode + RecoveryHint，B3）
   ▼
Replanner.replan(failed, status) ─► 有界修复 SubTask[]
   • RETRY  → 原样重发
   • ADJUST → 重发 + 类型化调整参数（offset/relax/force）
   • REROUTE→ 先导航到物体，再重发
   • SKIP   → 丢弃该步、继续
   • ESCALATE（触顶/无 hint）→ 停 + 说，交给用户
   ▼ 修复序列经 Phylax 重新审（P3 仍生效），再派发
   ▼ 每次尝试 + 失败 ─► TraceStore（只增，引用 node id B9）
```

## 2. `TraceStore`（`trace.py`）—— L4 情节记忆

stdlib sqlite，同 tempomem 的 `.smem`。一张只增 `episodes` 表；attempt/failure **永不删除**
（痕迹不可抹除 —— "清空"任务=轮换 `session_id`）。每行引用 tempomem **node id**（B9），故痕迹
可按物体查（`by_node(id)`）、按 session 查；`failures()` 是否定性学习视图。
`log_attempt`/`log_failure`；测试用 `:memory:`。

> **范围（D2）：** 开发计划设想这最终并入 tempomem 核心成单一存储。P4 阶段它在 `mindloop`、
> 引用 node id，已满足共享 id 空间要求；核心合并是推迟的、需跨仓协调的改动。

## 3. `Replanner`（`replan.py`）—— 类型化失败 → 有界修复

类型化失败 + 实例内计数器的纯函数（确定性、无网络、无 LLM —— LLM 兜底是未来钩子）。它在
**SubTask 层**（编译后）工作，复用失败步的 node id（B9）、调整参数，故无需名字回环。

- **上限（B2R）：** 每 `(verb, node-ids)` 目标 ≤ `max_per_target`（默认 2）；全局
  `max_total`（默认 6）防跨步死循环。任一触顶 ⇒ **升级**。
- **hint 映射（B3 `RecoveryKind`）：** `RETRY`→重发；`POSITION_OFFSET` /
  `ORIENTATION_RELAX` / `FORCE_ADJUSTMENT`→ADJUST（参数 `recovery`=kind）；`REPLAN`
  →REROUTE（导航 + 重发）；`SKIP`→跳过。无 hint ⇒ 升级。
- **升级话语**有卡时取技能卡的 `failure_hints`，否则默认。`reset()` 开新任务（计数清零；痕迹不动）。

## 4. Brain 集成（`brain.py`）

`Brain(replanner=…, trace=…)`（均 opt-in）。派发步变成有界**重规划回路**
（`_dispatch_plan` / `_repair`）：遇 `FAILED` 终态咨询 replanner，原地派发修复子任务、重复，直到
成功、跳过或升级。**安全仍生效** —— 修复序列派发前经 Phylax（P3）重审。**升级停整个 plan**、
把 `plan.speak` 换成修复话语；绝不死循环。未配 replanner 时派发就是 P1-P3 单发行为。

## 5. 文件

`trace.py`（新）· `replan.py`（新）· `brain.py`（`handle` 里的重规划回路）· `__init__.py` ·
`tests/test_replan.py`（新）。

**测试 / Exit（M-L3.3，P4 半）：** flaky 抓取 → 重规划调整 → 成功，两次尝试在痕迹里（可按
node id 查）；永久失败 → 有界重试 → 升级（停+说、无死循环）；类型 hint 映射（offset/replan/
retry/skip）；每目标 + 全局上限；无 replanner 保持 P1-P3。✅
