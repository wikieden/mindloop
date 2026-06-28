> 🌐 [English](../../../en/devplan/specs/P2-episteme-skill-cards.md) · **中文**

# P2 spec —— Episteme 技能卡库（M-L3.2）

**状态：** 已实现（2026-06-28）。实现 [DEV-PLAN.md](../DEV-PLAN.md) §P2。
**B2R 参考：** `techne_crystallization.md`、`household_task_taxonomy.md`、
`appliance_interaction.md`（程序性知识即数据；家电 affordance）。

## 1. 核心思想 —— 程序性知识即数据

`SkillCard` 是**怎么做的知识**（"洗衣服"、"煮意面"），声明式存储、不是代码。卡片是
**扁平步骤 + 规则**（K2 —— DAG 经 `schema_version` 预留、暂不建）。把卡片变成可派发
plan 的是 `instantiate()`；卡片本身是惰性数据，YAML 编写或 dict 构造。

`instantiate()` 的输出是 `Command` 元组 —— **与 LLM 规划器产出的中间表示相同**
（`plan.Command`）。所以技能卡和 LLM 是同一动词序列的两个**可互换来源**，都走同一条
下游编译（`compile_commands`：绑 node id B9、填 SubTask 元数据、本体 gate）。无第二
执行路径。

```
instruction
     │
     ▼
SkillCardPlanner.plan()                     ◀── 一个 plan.Planner
     │  检索最佳卡（语义 BYO-encoder | 关键词）
     │  命中?  ── 否 ──►  内层 LLM Planner  （回退，标记低置信）
     │  是
     ▼
extract_slots(instruction, card)            "wash the wool sweater" → {fabric: wool}
     ▼
instantiate(card, manifest, slots, prefs)
     │  • 触发 when 槽位匹配的 Rule          （wool → program=delicate）
     │  • 叠加规则 params，再叠 L5 偏好       （偏好优先；仅本体声明的键）
     │  • 解析每步对象槽位
     │  • 丢弃本体不支持的动词                （D3）
     ▼
tuple[Command]  ──►  compile_commands  ──►  SubTask[]  ──►  executor
```

## 2. Schema

`SkillCard`：`id`、`category`、`preconditions`、`rules`、`steps`、
`failure_hints`、`safety`、`provenance`、`schema_version`。

- **`SkillStep`** = `verb` + `target`（对象槽位或字面量；`"{category}"` 绑卡片
  category；空 ⇒ 无对象，如 `detect`）+ `params`（步级默认）。
- **`Rule`** = `when`（slot==value 条件，全满足）+ `set_params`（叠加）+
  `target_verb`（叠到哪个步动词；空 ⇒ 全部）。当 `when` 被情境槽位满足时规则**触发**。
- **`safety`** 存策略标注，供 **Phylax 层（P3）** gate。untrusted 来源带 `safety` 的
  卡片须先签名/审核才被采信（P3）；`provenance` 记来源。

## 3. 参数优先级（低 → 高）

1. 按动词查表默认（`compile_commands._VERB_TABLE`）
2. 步 `params`
3. 触发的 `Rule.set_params`
4. L5 `preferences`（仅本体为该动词声明的键）

用户明示偏好压过通用规则；二者都压过卡片默认。

## 4. 检索 —— BYO encoder

`SkillLibrary.retrieve(instruction, encoder=None, k=1)`：有 `Encoder` 则对
`category + id + 步动词` 做语义余弦；无则关键词重叠。无命中 ⇒ 空 ⇒ 规划器回退 LLM。
与 `tempomem.query` 同一 BYO 模式 —— 重语义后端可选、关键词兜底。

## 5. 回退被标记、绝不静默

`SkillCardPlanner` 无匹配卡片时交内层 LLM `Planner`，并**记日志标记低置信**（P2
契约：无卡 plan 被标记、不冒充策展知识）。未配 fallback 则返回 `()`。

## 6. 依赖

核心 **stdlib + 既有 numpy**；卡片从 dict 构造（`SkillCard.from_dict`），测试无依赖
无网络。YAML 加载器 `load_cards()` 在 **`skills`** extra 后惰性 import PyYAML ——
唯一出现第三方依赖处。

## 7. 本体改动（bodylink）

`g1d_manifest()` 加 **`operate_appliance`** 动词（`appliance_types`：
washer/stove/microwave/dishwasher），让洗衣/烹饪卡能驱动家电。`MockBody.dispatch()`
本就与动词无关 —— 无需改执行器。

## 8. 文件

`episteme.py`（新）· `plan.py`（`Command.params` + 合并）· `__init__.py`（导出）·
`cards/laundry_basic.yaml` + `cards/cook_pasta.yaml`（新）· `pyproject.toml`
（`skills` extra）· `tests/test_episteme.py`（新）· `bodylink/.../mock.py`
（+动词）· 各 CHANGELOG。

**Exit（M-L3.2，P2 半）：** 洗衣 + 烹饪卡对 MockBody 端到端跑通；wool/dark 规则解析到
正确程序；缺卡回退并标记。✅
