> 🌐 [English](../../../en/devplan/specs/P3-phylax-policy.md) · **中文**

# P3 spec —— Phylax 策略层（M-L3.2）

**状态：** 已实现（2026-06-28）。实现 [DEV-PLAN.md](../DEV-PLAN.md) §P3。
**B2R 参考：** `design_doc/02_systems/safety_architecture.md` —— §2（L3 语义级硬约束）、
§8（权限/人员半径/陌生人模式）、§9（守护层仲裁：信号优先级 + "上层想做永不覆盖下层不可以"）。

## 1. 范围 —— 只做大脑侧语义 tier

D4 的 Phylax 三层：**语义**（在大脑，这里）、符号-BT（在 `bodylink`）、反射（在固件）。
P3 只建**语义 tier** —— 可移植的声明式策略 gate。另两层推迟。

## 2. 位置 —— plan 与 dispatch 之间的 gate

```
route → plan → compile_commands → Plan ──► [ Phylax.check(plan, context) ] ──► dispatch
                                              │ 有 violation?
                                              ▼ 是
                                   阻断整个 plan：停 + 说，
                                   不重路由、不重试  (D4 §9)
```

`Brain.handle(..., safety_context=)` 在 manifest 门控编译（D3）**之后**、dispatch
**之前**跑 gate。任一 violation 阻断**整个** plan —— 啥都不派发（`statuses == ()`），
`HandleResult.violations` 带原因，`HandleResult.blocked` 为真，`plan.speak` 换成拒绝语。
gate **opt-in**：未配 `policy` ⇒ 照 P1/P2 派发。

## 3. 主导原则（B2R §9）

**单向收紧：上层的「想做」永不覆盖下层的「不可以」。** gate 只做减法 —— 只阻断、绝不
绕过安全约束去重路由/重试。安全类阻断是终态（停 + 说），区别于任务类失败（P4 可重规划）。

## 4. 声明式 `Policy` + `SafetyContext`

`Policy`（数据，按部署编写）：

| 字段 | 强制（B2R） |
|---|---|
| `adult_only_verbs` | §8 —— 刀具/电动工具类动词需 `role="adult"` |
| `supervised_only_verbs` | §2 —— 明火/高温需有成人监督 |
| `forbidden_node_ids` | 禁区 —— 子任务命中即拒 |
| `max_speed_mps_near_human`（+ `speed_param`） | §2/§8 —— 人员 1m 内，超速 locomotion 动词被拒 |
| `trusted_provenances` | untrusted 技能卡 gate（见下） |

`SafetyContext`（来自身份/感知层，**保守默认**，B2R §8「未知→保守」）：`role`
（`adult`/`child`/`guest`/`stranger`，默认 `stranger`）、`humans_within_1m`（默认
`False`）、`supervised`（默认 `False`）。

`Phylax.check(plan, context) -> tuple[Violation, ...]` 返回所有 violation（空 ⇒ 放行）。
每个 `Violation` 带 `rule`、`Severity`、机器 `message`、`subtask_id`、面向用户 `speak`。
调用方任一即阻断。

## 5. Untrusted 技能卡（社区卡 gate）

`SkillCard` 可带 `safety:` 标注 + `provenance`（P2）。带 `safety:` 且 `provenance`
**不在** `trusted_provenances`（默认仅 `{"builtin"}`）的卡，**被采信前即拒** —— 签名/审核
gate。`SkillCardPlanner(policy=phylax)` 调 `Phylax.vet_card` 跳过被拒的卡（回退 LLM 或空）。
无 `safety:` 的卡始终放行。

## 6. 文件

`phylax.py`（新：`Policy`、`SafetyContext`、`Violation`、`Severity`、`Role`、`Phylax`、
`refusal_speak`）· `brain.py`（`policy=` + `handle` 里的 gate）· `plan.py`
（`HandleResult.violations` + `.blocked`）· `episteme.py`（`SkillCardPlanner(policy=)`
审卡）· `__init__.py` · `tests/test_phylax.py`。

**测试 / Exit（M-L3.2，P3 半）：** 非成人执行刀具 → 拒；近人超速 → 拒；禁区目标 → 拒；
未签名 `safety:` 卡 → 拒；干净 plan 放行并派发；**每个派发的 plan 都过了 gate**，阻断带
可追溯 `violations`。✅
