# HD 知识库 — 上线优化与子 Agent 升级方案 (v1.1)

> 基于 `FEATURES.md` (v1.0, 2026-08-24) 现状评审 + 源码核对（`agent/graph.py` / `agent/state.py` / `api/chat.py` / `agent/nodes/answer.py`）产出的可执行优化方案。
> 定位：**「能跑」→「能上线」+「会答题」→「会办事」**。
> 本文遵循 `docs/file-writing-policy.md`：UTF-8 无 BOM。

---

## 0. 一句话结论

主链路（入库 → 检索 → 问答）已闭环、质量扎实，但当前是「个人自用的精致 Demo + 隧道裸奔」：

| 问题域 | 一句话诊断 |
|---|---|
| 🔐 安全 | 花生壳 HTTP 明文 + 无鉴权，任何人拿到域名就能用你的 LLM Key、看全部知识库 |
| ⚙️ 可靠 | 无备份、无进程守护、生产环境跑的是 Vite dev server |
| 🤖 能力 | Agent 只有 `retrieve -> answer`，只会答题不会办事；且 SSE 链路绕过了 LangGraph，图是装饰品 |
| 📏 质量 | RAG 效果零量化，改参数全靠「感觉」 |

---

## 1. 差距总览（三层）

| 层 | 内容 | 优先级 | 对应章节 |
|---|---|---|---|
| 安全基建 | 鉴权 / HTTPS / 生产构建 / 备份 / 进程守护 | **P0** | §3 |
| 质量保障 | RAG Eval / 监控告警 / 日志轮转 | P1 | §4 |
| 能力扩展 | Router + 4 个子 Agent | P1（与 P0 并行） | §2 |

---

## 2. 子 Agent 架构方案（核心）

### 2.1 目标架构

```
                    +---------------------------+
                    |  用户消息 / 定时任务       |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    |  Router 意图路由（新增）    |
                    |  便宜模型 · 非流式 · <1s    |
                    |  输出 intent + 改写 query   |
                    +---+---------+---------+---+
                        |         |         |
            chat/research      ingest     report
                        |         |         |
                        v         |         v
              +----------------+  |  +----------------+
              | 研究 agent（新增）|  |  | 周报 agent（新增）|
              | 改写→多轮检索    |  |  | 定时摘要·推送    |
              | →rerank→综述    |  |  +----------------+
              +-------+--------+  |         |
                      |           |         |
                      v           v         v
              +----------------+  +----------------+
              | answer（现有）   |  | 入库管家（新增） |
              | 综述/引用/流式   |  | 解析→打标→查重  |
              +----------------+  | →入库→结果卡片  |
                                  +----------------+
                      （飞书同步 agent：定时，revision 增量比对）

  =====================================================================
  共享工具层（全部复用现有代码，不重写）：
  hybrid_search · 11 个 parse_* · ingest.py · feishu_client · LLM factory
  =====================================================================
```

### 2.2 现状代码问题（源码核对结论）

1. **`api/chat.py` 绕过了图**：SSE 链路直接调 `hybrid_search()` + `answer_node_stream()`，`graph.py` 的 `build_graph()` 在流式路径中未被使用。本次升级顺势把编排权收回 LangGraph，Router 才有存在意义。
2. **多轮对话无 query 改写**：`_extract_query()` 只取最后一条 user 消息原文，追问句（"那它呢"）检索必挂。
3. **入库无智能**：`ingest.py` 纯管道，标题靠文件名、无标签、无查重。

### 2.3 State 扩展（`agent/state.py`）

```python
class AgentState(TypedDict, total=False):
  # ---- 现有字段不动 ----
  messages: list
  session_id: str
  query: str
  retrieved_chunks: list
  answer: str | None
  citations: list
  provider_override: str | None
  model_override: str | None
  base_url_override: str | None
  api_key_override: str | None
  reasoning_level_override: str | None
  step_count: int
  # ---- 新增 ----
  intent: str                  # chat | research | ingest | report
  rewritten_query: str         # Router 结合历史改写后的完整问句
  research_iterations: int     # 研究 agent 已检索轮数
  research_notes: list         # 多轮检索累计的中间发现
  ingest_result: dict          # 入库管家的结构化结果（标题/标签/摘要/note_id）
```

### 2.4 Graph 升级（`agent/graph.py`）

```python
"""LangGraph graph: router -> (research|ingest|retrieve) -> answer."""
from langgraph.graph import StateGraph, START, END
from app.agent.state import AgentState
from app.agent.nodes.router import router_node, route_by_intent
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.research import research_node
from app.agent.nodes.ingest import ingest_node
from app.agent.nodes.report import report_node
from app.agent.nodes.answer import answer_node


def build_graph():
  g = StateGraph(AgentState)
  g.add_node("router", router_node)
  g.add_node("retrieve", retrieve_node)
  g.add_node("research", research_node)
  g.add_node("ingest", ingest_node)
  g.add_node("report", report_node)
  g.add_node("answer", answer_node)

  g.add_edge(START, "router")
  g.add_conditional_edges("router", route_by_intent, {
    "chat": "retrieve",        # 现有链路保持不变
    "research": "research",    # 多轮检索后进 answer 综述
    "ingest": "ingest",        # 入库完直接结束（不走 answer）
    "report": "report",        # 周报生成完直接结束
  })
  g.add_edge("retrieve", "answer")
  g.add_edge("research", "answer")
  g.add_edge("answer", END)
  g.add_edge("ingest", END)
  g.add_edge("report", END)
  return g.compile()
```

**设计约束（第一版）**：子 agent 之间**不互相调用**，全部由 router 单层调度，避免循环图调试地狱。

### 2.5 Router 节点 [OK]（`agent/nodes/router.py` 新增）

**模型选择**：用便宜 + 快的模型（如 DeepSeek chat），非流式，目标延迟 < 1s。env 新增 `HD_ROUTER_MODEL` / `HD_ROUTER_BASE_URL`，未配置时 fallback 到主模型。

**提示词骨架**（放 `agent/prompts/router.txt`）：

```text
你是 HD 知识库的任务路由器。阅读对话历史和最新消息，只输出一个 JSON，不要任何其他文字：

{"intent": "<chat|research|ingest|report>", "rewritten_query": "<string>"}

判定规则：
- chat: 闲聊、简单事实问答，无知识库综合诉求
- research: 需要综合多篇资料、对比多个方案、深挖某个主题
- ingest: 消息里含 URL / 文件描述 / "存进来" "记一下" "帮我入库" 等指令
- report: 要求生成日报、周报、阶段总结、汇总摘要

rewritten_query 规则：
- 结合最近 3 轮对话，把指代词（"它" "这个" "上面说的"）补全成完整独立问句
- 只输出改写后的问句本身，不要回答它

示例：
历史: [user] 牛魔王有什么来历？  [assistant] 牛魔王是...
输入: "那他儿子呢？"
输出: {"intent": "research", "rewritten_query": "牛魔王的儿子（红孩儿）有什么来历？"}
```

**节点实现要点**：`chat.with_structured_output(RouterDecision)`（Pydantic schema 加 `intent: Literal[...]`），解析失败默认 `intent="chat"` + 原文 query——**路由失败永远降级到现有链路，不能阻断主流程**。

### 2.6 研究 agent [OK]（`agent/nodes/research.py` 新增）

解决：多轮追问检索挂、无综述能力。

```python
MAX_ITER = 3  # 检索轮数上限，防止成本失控

async def research_node(state: AgentState) -> dict:
  collected, seen = [], set()
  queries = [state["rewritten_query"]]
  for i in range(MAX_ITER):
    q = queries[i]
    chunks = hybrid_search(q, top_k=5, ...)     # 复用现有混合检索
    new = [c for c in chunks if (c["note_id"], c["chunk_index"]) not in seen]
    collected += new; seen.update(...)
    if len(collected) >= 8:                      # 素材够了提前停
      break
    queries.append(generate_followup(collected, state))  # LLM 生成下一个检索角度
  return {"retrieved_chunks": collected, "research_iterations": i + 1}
```

- `generate_followup`：一次轻量 LLM 调用，输入已收集素材的标题列表 + 原问题，输出「还缺什么角度」的下一个 query。
- 综述阶段**复用现有 `answer_node`**：research 只负责把 `retrieved_chunks` 装满，answer 的 `ANSWER_INSTRUCTIONS` 加一段 research 模式说明（要求分点综合、标注角度而非只罗列）。
- 可选增强：接 rerank（SiliconFlow `bge-reranker-v2-m3`），在 `collected` 进 answer 前精排取 top 8。

### 2.7 入库管家 agent [OK]（`agent/nodes/ingest.py` 新增）

解决：入库「无脑进库」，标题乱、无标签、重复不查重。

```
触发（消息含 URL / 用户上传）
  -> 解析（复用 11 个 parse_*）
  -> LLM 元数据抽取（一次调用，structured output）：
       {title: 吸引人的中文标题 ≤30 字,
        tags: 3~5 个,
        summary: 一句话摘要 ≤60 字}
  -> 查重：title/summary 做 FTS5 相似检索，score > 0.8 时提示「疑似重复：xxx」
       （第一版只提示不阻断，人在前端确认）
  -> 入库（复用 ingest.py 现有 chunk -> embed -> Chroma + FTS5 链路）
  -> 返回结构化 ingest_result，前端渲染成「入库结果卡片」
```

**价值**：标签和查重做好了，研究 agent 的检索质量直接受益（FTS5 关键词命中依赖干净元数据）。

### 2.8 周报 agent [OK]（`agent/nodes/report.py` 新增 + `main.py` 调度）

- **手动触发**："给我生成本周知识库周报" → router → report_node。
- **定时触发**：`APScheduler`（cron，如每周一 9:00）查询近 7 天新增/更新的 notes，按 tag 分组，LLM 生成 Markdown 周报，**存为一条 note 入库**（周报本身可被检索）+ 可选推送（飞书 webhook bot）。
- env：`HD_REPORT_CRON="0 9 * * 1"`、`HD_REPORT_WEBHOOK=""`（空则只入库不推送）。

### 2.9 飞书同步 agent [OK]（改造 `feishu_sync.py`）

解决：全量跳过式同步，文档改了不重抓。

- `Note` 表新增 `source_revision: str | None` 字段（SQLite 加列，老数据为 NULL 视为未知、首次同步补写）。
- 同步时对比飞书节点的 `edited_time` / obj_token 版本号：
  - 无变更 → `skipped`
  - 有变更 → **删旧 chunk（Chroma where note_id + FTS5）→ 重走入库链路** → 更新 revision
- 变更时可选：把「哪个文档改了」写进一条 sync_log note，供周报 agent 消费。

### 2.10 SSE 协议扩展 [OK]（`api/chat.py`）

现有事件不动，新增两类：

```
event: stage   {"stage": "router",   "status": "done", "intent": "research", "ms": 620}
event: stage   {"stage": "agent",    "status": "started", "agent": "research", "iteration": 1}
event: stage   {"stage": "agent",    "status": "done", "agent": "research", "iterations": 2}
event: ingest  {"title": "...", "tags": [...], "summary": "...", "note_id": 42, "duplicate_of": null}
```

前端 `StreamingIndicator` 直接消费新 stage 字段（"意图识别中..." → "研究 agent 第 2 轮检索..."）。

### 2.11 前端改动点 [OK]

| 组件 | 改动 |
|---|---|
| `StreamingIndicator.vue` | 支持新 stage（router / agent / iteration） |
| 新增 `IngestResultCard.vue` | 渲染 `event: ingest` 的结构化结果（标题/标签/摘要/查重提示） |
| `ChatView.vue` | 入库指令的输入提示（placeholder 加一句"可以说：把这个链接存进来"） |
| 周报 | 设置页加 cron 配置项 + 「立即生成」按钮 |

---

## 3. P0 安全基建清单（对外可访问前必须完成）

| # | 项 | 做法 | 验收 |
|---|---|---|---|
| 1 | **鉴权** | 最低限度：反代层 Basic Auth（nginx/caddy）；理想：FastAPI dependency 校验 `Authorization: Bearer <HD_ACCESS_TOKEN>`，env 下发，前端 localStorage 带上 | 无 token 请求 401 |
| 2 | **HTTPS** | 花生壳换 HTTPS 隧道，或改用 Cloudflare Tunnel（免费 + 自带 TLS + 顺带挡扫描） | 浏览器锁标志 + curl `https://` 通 |
| 3 | **生产构建** | `npm run build` 出 `dist/`，nginx 托管静态 + `/api` 反代 8001；**下线 Vite dev server 对外暴露** | 访问域名不再出现 Vite HMR websocket |
| 4 | **备份** | 任务计划每日 03:00 跑 `scripts/backup.ps1`：`robocopy data/ D:\backups\hd\%date% /MIR` + 保留最近 14 份；Chroma 先停写或用 SQLite `VACUUM INTO` | 手动触发一次能恢复 |
| 5 | **进程守护** | NSSM：`scripts/install-service.ps1` 已提供；默认仍用 `scripts/start-all.ps1` 手动启动 | `nssm status hd-backend` |

> 顺带修：`logs/` 加 `RotatingFileHandler`（10MB × 5 份），现在 uvicorn 日志无限增长。

---

## 4. RAG Eval 方案（P1）[OK]

和 CRM 智能体 Eval 开发线同一套方法论，先建尺子再调参：

1. **Golden set**：`scripts/rag_eval/golden.jsonl`，30~50 条 `{query, expect_note_ids: []}`（覆盖：精确事实 / 多跳综合 / 追问改写 / 应拒绝的闲聊）。
2. **指标**：Recall@5、MRR、闲聊误命中率（应 0 引用时给出引用的比例，越低越好）。
3. **脚本**：`scripts/rag_eval/run.py`，直连 `hybrid_search`，输出 markdown 报告，改 `min_score` / 权重 / embedding 后跑回归。
4. **接入**：和 `table_tests/run_all.py` 并列为发版前自检项。

---

## 5. 落地路线图

| 阶段 | 内容 | 交付物 |
|---|---|---|
| **第 1 周** | P0 安全五件套（§3）+ 日志轮转 | 鉴权 + HTTPS + 生产构建 + 备份 + NSSM 全部验收通过 |
| **第 2 周** | Router + 研究 agent（§2.5/2.6）+ SSE 扩展 | 多轮追问可答；图接管 SSE 编排；golden set v1（20 条） |
| **第 3 周** | 入库管家 + 周报 agent（§2.7/2.8） | 入库结果卡片；第一份自动周报 |
| **第 4 周起** | 飞书增量同步 + rerank + Eval 扩充到 50 条 | 增量同步生效；每次改动有回归报告 |

**并行原则**：子 agent 开发与 P0 安全可并行；但**对外给人用之前 P0 必须全绿**——功能越多，裸奔域名越值钱。

---

## 6. 验收标准

| 能力 | 验收用例 |
|---|---|
| 意图路由 | "那它呢？" → router 输出改写 query，检索命中正确文档 |
| 研究 agent | "对比知识库里 A 方案和 B 方案" → 分点综述 + 双侧引用 |
| 入库管家 | 发一条 URL → 30s 内返回标题/标签/摘要卡片；重复发 → 出现查重提示 |
| 周报 | 周一 9:00 自动生成周报 note；说"生成本周周报"立即出 |
| 飞书增量 | 改一篇飞书文档 → 下轮同步 `updated>=1`，旧 chunk 不残留 |
| 安全 | 无 token 401；HTTP 域名失效；杀进程 5s 自动复活；备份可恢复 |

---

## 7. 风险与注意事项

1. **Router 成本**：每条消息多一次 LLM 调用。用便宜模型 + 短 prompt 控制在几百 token；闲聊占比高的场景可前端加「快速模式」跳过 router。
2. **研究 agent 循环失控**：`MAX_ITER=3` 硬上限 + 每轮素材够 8 条提前停。
3. **入库管家写库**：是唯一写数据库的 agent，查重第一版「只提示不阻断」，确认逻辑稳定后再考虑自动去重。
4. **换 embedding 的老约束**依然生效：所有 agent 共用 `hybrid_search`，换 embedding 模型后全库 reembed。
5. **graph 接管 SSE 后**保留 `chat.py` 直调路径作为降级开关（env `HD_USE_GRAPH=false`，已实现在 config.py），出问题可一键回退。

---


## 8. v1.1 验收记录（2026-08-24）

| 项 | 状态 | 验证方式 |
|---|---|---|
| Phase 1 花生壳下线 | OK | rg 全仓搜 11gv92/花生壳/vicp 只剩历史 doc |
| Phase 2 日志轮转 | OK | main.py RotatingFileHandler 10MB x 5 |
| Phase 2 备份脚本 | OK | scripts/backup.ps1 手动可跑 |
| Phase 2 NSSM 脚本 | OK | scripts/install-service.ps1 按需启用 |
| Phase 3 state.py 扩展 | OK | intent/rewritten_query/research/ingest/report 字段 |
| Phase 3 router.py | OK | 4 intent 条件分发烟测通过 |
| Phase 3 research.py | OK | import + AST OK |
| Phase 3 ingest.py | OK | import + AST OK |
| Phase 3 report.py | OK | import + AST OK |
| Phase 3 graph.py | OK | graph.astream 7 节点 |
| Phase 3 retrieve 改写优先 | OK | rewritten_query 优先 |
| Phase 3 chat.py 接管 SSE | OK | HD_USE_GRAPH 切换 |
| Phase 4 Feishu 增量 | OK | source_revision + _drop_and_reingest |
| Phase 4 sync API force_full | OK | body 含 force_full 字段 |
| Phase 5 RAG Eval | OK | golden.jsonl 6 条 + run.py |
| Phase 6 SSE 前端 | OK | IngestResultCard + StreamingIndicator + ChatView |
| Phase 7 文档同步 | OK | OPTIMIZATION.md v1.1 + FEATURES.md |

### 已知未做（按需触发）

- 鉴权（公网恢复前不需要）
- HTTPS（同上）
- NSSM 安装（用户按需）
- Task Scheduler 备份挂载（用户按需）
- 多租户 / 移动端 / MCP（不在 v1.x 范围）
