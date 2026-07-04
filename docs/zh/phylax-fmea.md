> 🌐 [English](../en/phylax-fmea.md) · **中文**

# Phylax FMEA —— 失效模式分析 → 策略覆盖（T5-10）

关闭长期未决项"策略来自 B2R 硬约束枚举，而非失效模式分析"。方法：按通道枚举
家用机器人可能伤人/破坏信任的方式，逐条对照现有防线；无防线的模式落成代码
（本轮产出 `conservative_policy()` 预设，并确认一处结构性覆盖）。

## 失效模式 × 防线

| # | 失效模式 | 防线 | 状态 |
|---|---|---|---|
| 1 | 小孩指挥危险动词 | `adult_only_verbs`（permission.adult_only） | 已覆盖 |
| 2 | 小孩指挥良性动词的危险*取值*（灶台、刀具） | D1 `adult_only_verb_params`（permission.adult_only_param） | 已覆盖；`conservative_policy()` 出厂预设 |
| 3 | 访客/陌生人被带进私密区域 | Q6 `guest_blocked_regions` + 未知区域拒绝（region.*） | 已覆盖 |
| 4 | 错误服务角色进入受限区域 | D-A `service_permitted_regions`（grant ∩ need，D-O） | 已覆盖 |
| 5 | 人近处高速移动 | `max_speed_mps_near_human`（保守预设 0.2） | 已覆盖 |
| 6 | 过敏原递给状态未知者 | D-K 菜单不变式，fail-closed（allergy.*） | 已覆盖 |
| 7 | 不可信技能卡放松安全 | `trusted_provenances` + learned 卡无 safety 键（D-L） | 结构性覆盖 |
| 8 | 打断/问询回答夹带被禁动作 | 全部重规划路径过同一 gate 复审 | 已覆盖（有测试） |
| 9 | 访客劝说机器人换角色/改策略 | 角色：不可自我提升（D-O）；策略：`replace_policy` 仅 adult 且打断/问询路径不可达 | 已覆盖（T5-10） |
| 10 | 可靠度分数买通安全 | Phylax 从不读 `VerbSpec.reliability`（D-P 守则） | 已覆盖（有测试） |
| 11 | 离线降级放松 gate | P7.4 离线门整体换入、只紧不松；推荐填 `conservative_policy()` | 已覆盖 |
| 12 | 拖地后地面湿滑，有人走入 | D-D `mop` 展开自带 `warn_wet_floor` 首尾夹 —— 结构性而非策略 | 结构性覆盖 |
| 13 | 物理故障（碰撞）反复重试且靠近人 | Replanner 上限（≤2/目标，≤6/任务）后升级停机；重试带 `negation_constraints` | 已覆盖 |
| 14 | 人近处操作热液体 | **缺口** —— 需身体侧热/近距信号（今日在 L2 之下） | 延后到 D3 真机轨 |
| 15 | 携带易碎物时电量耗尽 | 类型化 `BATTERY_LOW` 升级；优雅放下属身体/BT 层 | 延后（身体层） |

## 结论

- 新增：`conservative_policy()` 预设（模式 2/5/11）+ `Phylax.replace_policy`
  仅 adult 覆写（模式 9）+ 重试携带 `negation_constraints`（模式 13）。
- 未决（卡硬件）：模式 14–15 需身体侧信号 —— 随 D3 真机轨跟踪，不做 Phylax 规则。
