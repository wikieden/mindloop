> 🌐 [English](../../../en/devplan/specs/P5-dialogue-full-loop.md) · **中文**

# P5 spec —— 对话 + 完整 S2 回路（M-L3.3）

**状态：** 已实现（2026-06-28）。实现 [DEV-PLAN.md](../DEV-PLAN.md) §P5，关 **M-L3.3**
（P4 + P5）。**B2R 参考：** `05_scenarios/e2e_walkthrough.md`、`breakfast_e2e.md`
（多任务：任务 + 问答 + 社交、逐人身份上下文、多步、重规划）。

## 1. 净新增

单指令回路 P4 时已端到端跑通：
`route → plan → compile (D3) → policy (P3) → dispatch → 有界重规划 (P4) → trace`。
P5 加两样把它从单发变**对话**，再在复现的家庭场景上证明整体：

1. **多轮对话** —— `Conversation` 携带轮次历史，问答/chat 轮以近期轮次为上下文作答
   （追问"另一个" → 对前一轮解析）。记忆接地（扩 `ask`）。
2. **L5 偏好叠加** —— 逐人偏好（`PreferenceStore`）覆盖技能卡参数默认，过滤到本体声明的动词。
3. **端到端场景测试** —— 一段多轮对话走 问答 → 任务(成功) → 任务(重规划→恢复) → 任务(安全阻断)，
   全引用+全痕迹、无真网络。这就是 M-L3.3 集成证明。

## 2. 多轮对话（`dialogue.py`）

- **`Turn`** = `(instruction, HandleResult)`。**`Conversation`** = 有序轮次列表 +
  `history_text(n)` 渲染近 `n` 轮作上下文。
- **`Brain.converse(instruction, conversation=None, *, person="", safety_context=None)
  -> HandleResult`** —— 把对话近期历史穿进 `handle` 跑（问答/chat 轮既记忆接地*又*对话接地），
  然后追加该轮。单发 `handle` 不变（对话 opt-in）。
- 任务轮规划不需对话上下文（MVP 里指令自足）；历史喂**作答**，那才是追问出现处。

## 3. 偏好叠加（L5，D2）

- `PreferenceStore` 加 **`all(person) -> Mapping[str, str]`**（某人完整偏好图）外加 `get`。
  具体内存 **`DictPreferenceStore`** 供测试/部署；真后端（如 Mem0）树外（D2 —— 偏好出记忆核，
  为生命周期/隐私）。
- `Brain(preferences=…)` + `handle(..., person=…)`：任务 plan 编译后，大脑把某人偏好**叠到每个
  SubTask 的 params**、过滤到本体为该动词声明的参数键（`manifest` 门控，偏好不能注入未知参数）。
  偏好压过卡片/规则默认 —— 用户明示压过通用默认。在大脑里编译后做（不改 `Planner` 协议），故对
  LLM 和技能卡 plan 一视同仁。

## 4. 完整回路即一段对话

```
person + instruction（第 N 轮）
   │  Conversation 历史 ──┐
   ▼                      ▼
Brain.converse → handle:
   route ─ question/chat ─► ask(+ 对话历史) ─► 带引用 Answer
        └ task ─► plan ─► compile (D3) ─► 偏好叠加 (L5)
                        ─► Phylax (P3) ─► dispatch ─► 有界重规划 (P4)
                        每步 ─► TraceStore (B9 node id)
   ► HandleResult ─► 追加进 Conversation
```

回路本身没变；P5 用对话状态 + 偏好叠加包住它，并在场景上演示。

## 5. 文件

`dialogue.py`（新：`Turn`、`Conversation`）· `preference.py`（`all` + 具体
`DictPreferenceStore`）· `brain.py`（`converse`、`person=`、`preferences=`、偏好叠加）·
`__init__.py` · `tests/test_dialogue.py`（新，含端到端场景）。

**测试 / Exit（M-L3.3）：** 一段多轮对话走 问答 → 任务(成功) → 任务(重规划→恢复) → 任务(安全
阻断)，对 MockBody / `_FlakyBody` 端到端，每答引用 node id、每次派发入痕迹；追问对前文解析；某人
偏好覆盖卡片默认（manifest 门控）。完整 S2 回路无真网络复现。✅
