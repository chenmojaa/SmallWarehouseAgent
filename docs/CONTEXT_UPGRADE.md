# HD 上下文升级 — 实施文档 (v1.0)

> 目标：把「上下文管理权」从**前端**收回**服务端**，让多轮对话真正可用，并根治两个已知 bug。
> 依据：源码核对（`answer.py` / `chat.py` / `state.py` / `graph.py` / `stores/chat.ts` / `ChatView.vue`）+ 参考项目五层上下文架构（YAML → runtime → input_context → State+checkpointer → prompt 渲染）。
> 遵循 `docs/file-writing-policy.md`（UTF-8 无 BOM）。

---

## 实施状态（截至 2026-08-25）

| Phase | 项目 | 状态 | Commit |
|---|---|---|---|
| 1.1 | `answer.py` 历史滑窗 | [x] | `262fa84` |
| 1.2 | `chat.ts` `clear()` 保护 + `loadFromSession` inFlight 解耦 | [x] | `b9d8891` |
| 2.1 | `db.py` `get_messages(session_id, limit)` | [x] | `f2af3a2` |
| 2.2 | `chat.py` `_build_initial_state` 用 DB 历史覆盖前端 payload | [x] | `f2af3a2` |
| 3.1 | `state.py` `messages: Annotated[list, operator.add]` | [x] | `d07072d` |
| 3.2 | `graph.py` 编译挂 `MemorySaver` checkpointer | [x] | `d07072d` |
| 3.3 | `chat.py` `thread_id` config + messages 累加合并 | [x]（partial，未切 stream_mode）| `d07072d` |
| 3.4 | `answer.py` 删 Phase 1 滑窗补丁 | [ ] 延后 | — |
| 3.5 | 前端 `chat.ts` 只发当前 turn | [x] | `293ff16` |
| 4.1 | `prompts/config.yaml` + 默认回退 | [x] | `9e7cb3f` |
| 4.2 | `format_context` 抽到 `app/agent/context.py` | [x] | `f998114` |

**3.4 延后原因**：当前节点均不回 `messages`，checkpointer 里的 `state.messages` 只积累 user 消息、缺 assistant 消息。若直接删 `answer.py` 的滑窗，`_build_messages` 会读到不完整的历史（看不到之前的助手回复），反而退化。要做 3.4 需要让 `answer_node` 把助手回复 append 进 state.messages——这是另一种破坏性更大的改动，建议单独立项并配合回归测试。

**3.3 partial 说明**：保留了文档原本的 default stream event 模式，只加了 `config` 传入 `thread_id`，没有切到 `stream_mode="messages"`。后者会改变 SSE 形状（从 node-event 流变成 LLM-token 流），属于另一个独立重构。

每项改动落地时都写了对应的烟雾测试（执行后即删，未入库）。

---



## 0. 现状问题清单（三个）

| # | 问题 | 根因 | 文件 |
|---|---|---|---|
| B1 | 追问必挂 [x] 修于 `262fa84` |（"那它呢"答非所问） | `answer.py::_build_messages` 只发 `SystemMessage + 当前问题`，历史收了但从没进 LLM | `backend/app/agent/nodes/answer.py` |
| B2 | 切页面回来丢思考提示 [x] 修于 `b9d8891` | | `chat.ts::clear()` 把 in-flight 的 messages/snapshot 清零，绕过了 snapshot 恢复逻辑 | `frontend/src/stores/chat.ts` |
| B3 | 上下文由前端全量重发 [x] 修于 `f2af3a2` + `293ff16` | | payload 越聊越大 + 前端可伪造/篡改历史 + 前后端状态易不一致 | `chat.ts` send / `chat.py` |

---

## 1. 目标架构

```
现在（客户端管）                          目标（服务端管）
┌─────────────┐                        ┌─────────────┐
│ 前端 Pinia  │  全量 messages          │ 前端        │  只发新消息 + session_id
└──────┬──────┘  ────────────────▶     └──────┬──────┘  ────────────────▶
       │                                     │
       v                                     v
┌─────────────┐                        ┌─────────────┐
│ answer.py   │  历史没用上(B1)         │ 服务端      │  从 DB / checkpointer 恢复历史
└──────┬──────┘                        └──────┬──────┘
       v                                     v
      LLM                                  LLM
```

**分四步走，每步独立可验证、可回滚**：

```
Phase 1  止血（1h）      → 历史进 LLM + clear() 修复          → 修 B1、B2
Phase 2  服务端接管（半天） → 后端从 DB 读历史，不再信任前端     → 修 B3，低风险
Phase 3  checkpointer 图接管（与 Router 同期） → LangGraph 原生状态恢复
Phase 4  配置化 + 注入点（配合 Router） → 提示词三层覆盖 + 注入点拆分
```

> 为什么把 checkpointer 拆成 Phase 3 而不是和 Phase 2 合并：Phase 2 用**已有的 ChatMessage 表**做真相源，改动小、立刻见效；checkpointer 需要动 graph 编译 + answer 流式集成，和 Router 一起做能避免返工。

---

## 2. Phase 1：止血

### 2.1 [x] `answer.py`  [commit `262fa84`] — 历史滑窗进 prompt（修 B1）

**改动点**：`_build_messages()` 加历史滑窗。

```python
# 顶部 import 增加 AIMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


def _build_messages(state: AgentState):
  chat = _build_model(
    provider=state.get("provider_override"),
    model=state.get("model_override"),
    api_key=state.get("api_key_override"),
    base_url=state.get("base_url_override"),
    reasoning_level=state.get("reasoning_level_override"),
  )
  chunks = state.get("retrieved_chunks") or []
  question = state.get("query", "") or "(no question)"
  instructions = ANSWER_INSTRUCTIONS.replace("<<CONTEXT>>", _format_context(chunks)).replace("<<QUESTION>>", question)

  msgs = [SystemMessage(content=instructions)]

  # ---- 新增：历史滑窗，最近 8 条（约 4 轮）----
  history = [
    m for m in (state.get("messages") or [])
    if m.get("role") in ("user", "assistant") and m.get("content")
  ]
  # 前端 history 里最后一条就是当前问题，跳过防止重复
  if history and history[-1]["role"] == "user" and history[-1]["content"] == question:
    history = history[:-1]
  for m in history[-8:]:
    msgs.append(HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"]))

  msgs.append(HumanMessage(content=question))
  return chat, msgs, chunks
```

**滑窗为什么是 8 条**：覆盖绝大多数追问场景；token 成本线性可控；过长历史会稀释 LLM 注意力。

### 2.2 [x] `chat.ts`  [commit `b9d8891`] — `clear()` 保护流状态（修 B2）

**改动点一**：`clear()` 动作加 in-flight 保护。

```ts
clear() {
  // 有后台在跑的流时，切到非会话页（知识库/Skill/搜索）只是离开当前视图，
  // 不能把流状态打掉——等用户切回来再恢复。
  if (this.isStreaming && this.streamingSessionId !== null && this.messages.length > 0) {
    this.streamingSnapshot = [...this.messages]
    this.sessionId = null   // 只清当前视图指针
    this.error = null
    return
  }
  this.sessionId = null
  this.messages = []
  this.streamingSnapshot = null
  this.error = null
},
```

**改动点二**：`loadFromSession()` 的 in-flight 判断与 `messages.length` 解耦。

```ts
// 改前：
// const inFlight = this.streamingSessionId !== null && this.messages.length > 0
// 改后：
const inFlight = this.isStreaming && this.streamingSessionId !== null
```

**原理**：把「是否在流」这件事和 `messages.length` 解耦——`clear()` 不再误杀，`loadFromSession` 里那段 `streamingSnapshot && streamingSessionId === sessionId` 的恢复路径（原本就写好了）就能正常触发。

### 2.3 [x] Phase 1 验收

| 用例 | 预期 |
|---|---|
| 问「牛魔王有什么来历」→ 追问「那他儿子呢」 | 应答出红孩儿，不答非所问 |
| 发消息 → 点「知识库」→ 点回原会话 | 思考提示不消失，流继续正常渲染 |

---

## 3. Phase 2：服务端接管上下文（修 B3）

**核心思想**：后端以 `ChatMessage` 表为真相源读取历史，不再信任前端 payload。前端仍可发送 messages（兼容过渡），但后端用 DB 历史为准。

### 3.1 [x] `storage/db.py`  [commit `f2af3a2`] — 新增读历史函数

> ⚠️ 需确认：`db.py` 现有 `create_session` / `append_message` 两个已核对；是否已有「按 session 读消息」函数需查一下，没有就新增。

```python
def get_messages(session_id: str, limit: int = 16) -> list[dict]:
  """按 session 取最近 N 条消息，旧→新排序，返回 {role, content}。"""
  from app.storage.db import ChatMessage
  rows = (
    session.exec(
      select(ChatMessage)
      .where(ChatMessage.session_id == session_id)
      .order_by(ChatMessage.created_at.desc())
      .limit(limit)
    ).all()
  )
  return [{"role": m.role, "content": m.content} for m in reversed(rows)]
```

### 3.2 [x] `chat.py`  [commit `f2af3a2`] — 用 DB 历史覆盖前端 payload

在 `initial_state` 组装处，用 DB 历史替换 `body.messages`：

```python
history = get_messages(session_id, limit=16) if session_id else []
# 追加当前 query 作为最新一条
history.append({"role": "user", "content": query})

initial_state = {
  "messages": history,          # ← 真相源：DB 历史 + 当前问题
  "session_id": session_id,
  "query": query,
  # ... 其余字段不变
}
```

**效果**：即使前端伪造/清空了 messages，后端也以自己 DB 里的历史为准。前端 `chat.ts` 的 `history` 字段暂时保留（过渡期），Phase 3 起不再需要。

### 3.3 [x] Phase 2 验收

| 用例 | 预期 |
|---|---|
| 刷新页面后追问上一轮内容 | 仍能接上（历史来自 DB，不依赖前端内存） |
| 用 curl 只发 `{"messages":[{"role":"user","content":"那他儿子呢"}]}` + session_id | 后端仍能还原历史并答对 |

---

## 4. Phase 3：checkpointer 图接管（与 Router 同期）

> 这一阶段和 `OPTIMIZATION.md` §2.4「图接管 SSE 编排」是同一件事，建议和 Router 节点一起做，避免动两次 graph。

### 4.1 [x] `state.py`  [commit `d07072d`] — messages 改累加式

```python
import operator
from typing import Annotated

class AgentState(TypedDict, total=False):
  messages: Annotated[list, operator.add]   # 新消息追加，不是覆盖
  # 其余字段不动
```

### 4.2 [x] `graph.py`  [commit `d07072d`] — 编译挂 checkpointer

```python
# 先跑通用内存版（零依赖），验证 OK 再换 SQLite
from langgraph.checkpoint.memory import MemorySaver

def build_compiled_graph():
  from app.agent.graph import build_graph
  return build_graph().compile(checkpointer=MemorySaver())
```

> ⚠️ 需确认：LangGraph 1.2 的 SQLite checkpointer 确切导入路径（`langgraph-checkpoint-sqlite` 依赖）。持久化版用 `AsyncSqliteSaver.from_conn_string("data/agent_history.db")`。先用 `MemorySaver` 证明「thread_id 恢复历史」能跑通，再换 SQLite。

### 4.3 [x-partial] `chat.py`  [commit `d07072d`] — 改走 `graph.astream`

```python
config = {"configurable": {"thread_id": session_id}}
input_state = {"messages": [{"role": "user", "content": query}]}   # 只有新消息

async for chunk in graph.astream(input_state, config=config, stream_mode="messages"):
  # 现有 SSE 产出逻辑（session/stage/delta/citations/done）搬进来
```

### 4.4 [ ] 延后 `answer.py`  (见上文 3.4 延后原因) — 删掉 Phase 1 的历史滑窗补丁

`state["messages"]` 此时由 checkpointer 自动累加，已经是全量历史；滑窗（取最后 8 条）在节点内做即可。

### 4.5 [x] 前端  [commit `293ff16`] `chat.ts` — 只发新消息 + session_id

```ts
// send() 里 history 字段改为：
const history = [{ role: 'user', content: text }]   // 只发这一条
// session_id 仍传 this.sessionId
```

### 4.6 [x] 保命开关  (HD_USE_GRAPH 此前已存在，`f2af3a2` 起配合 DB 历史)

```python
# chat.py 顶部
import os
if os.getenv("HD_USE_GRAPH", "false").lower() == "true":
    # 走 graph.astream
else:
    # 走老的直调路径（Phase 2 的 DB 历史版）
```

**过渡期**：`ChatMessage` 表照旧写（侧栏历史 UI 依赖），checkpointer 是图状态源。两者短期并存；长期 `loadFromSession` 改读 checkpointer 后二合一。

---

## 5. [x] Phase 4：配置化 + 注入点

| 项 | 改动 |
|---|---|
| 提示词配置化 [x] (`9e7cb3f`) | `ANSWER_INSTRUCTIONS` 挪到 `backend/app/agent/prompts/config.yaml`，加载顺序「默认值 → YAML → 请求参数」 |
| 注入点拆分 [x-partial] (`f998114`) | 「模型选择」 (`llm/factory.py`) / 「system prompt」 (`prompts/`) / 「检索注入」 (`context.py`) 三个关注点已拆到独立模块。Router 节点落地时，把「模型选择 / system prompt / 检索注入」拆成独立函数，未来升级成 middleware 式（对齐参考项目 `context_middlewares.py` 模式） |

---

## 6. 全局验收标准

| # | 能力 | 验收用例 |
|---|---|---|
| 1 | 多轮上下文 [x] | 连续 5 轮追问均能正确指代，不答非所问 |
| 2 | 状态不丢 [x] | 流式中切页再切回，思考提示与流不中断 |
| 3 | 真相源唯一 [x] | 前端清空 messages 后，后端仍能还原历史 |
| 4 | 可回滚 [x] | `HD_USE_GRAPH=false` 一键退回直调路径 |

---

## 7. 回滚方案

| 阶段 | 回滚动作 |
|---|---|
| Phase 1 | `git checkout` 两个文件即可，无副作用 |
| Phase 2 | 同上；DB 只加了只读函数，无 schema 变更 |
| Phase 3 | `HD_USE_GRAPH=false` 退回 Phase 2 直调路径 |
| Phase 4 | 配置读不到时 fallback 到硬编码默认值 |

---

## 8. 涉及文件清单

| 文件 | Phase | 改动类型 |
|---|---|---|
| `backend/app/agent/nodes/answer.py` | 1 / 3 / 4 | [x] 1.1 滑窗 (`262fa84`); [x] 4.1 prompt 改 YAML (`9e7cb3f`); [ ] 3.4 删滑窗延后 |
| `frontend/src/stores/chat.ts` | 1 / 3 | [x] 1.2 clear() 保护 (`b9d8891`); [x] 3.5 只发新消息 (`293ff16`) |
| `backend/app/storage/db.py` | 2 | [x] 新增 `get_messages(session_id, limit)` (`f2af3a2`) |
| `backend/app/api/chat.py` | 2 / 3 | [x] 2.2 DB 历史 (`f2af3a2`); [x-partial] 3.3 thread_id config，未切 stream_mode (`d07072d`) |
| `backend/app/agent/state.py` | 3 | [x] messages 改 `Annotated[list, operator.add]` (`d07072d`) |
| `backend/app/agent/graph.py` | 3 | [x] 挂 `MemorySaver` checkpointer (`d07072d`) |

---

## 9. 依赖清单

| 依赖 | Phase | 说明 |
|---|---|---|
| `langgraph-checkpoint-sqlite` | 3 | **未加**：当前 `MemorySaver` 满足基础需求；升级到 SQLite 持久化时再加。 |
| `aiosqlite` | 3 | **未加**：同上。 |

> Phase 1-4 **零新增依赖**（PyYAML 早就在依赖里）。langgraph-checkpoint-sqlite / aiosqlite 留待持久化升级时再装。
