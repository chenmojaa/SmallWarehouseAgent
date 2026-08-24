# HD 个人知识库 — 功能现状 (v1.0)

> 一份给「想了解这个项目能干什么、怎么用、怎么改」的人看的功能总览。
> 最近更新：2026-08-24（含 v0.7-v0.9 RAG 链路、表格识别三层、飞书知识库集成）

---

## 0. 一句话定位

HD = **本地优先的个人/团队 Second Brain**。把散落的文章 / 文件 / 对话 / 飞书文档统一塞进一个可检索的知识库，用自然语言向 LLM 提问，答案带原文引用；底层 RAG 走「混合检索 + Markdown 表格感知」，支持多 LLM 自由切换，当前为本地访问模式（花生壳公网隧道已下线）。

---

## 1. 技术栈

| 层 | 技术 | 备注 |
|---|---|---|
| 后端框架 | FastAPI 0.115+ | 异步 REST + SSE 流式 |
| Agent / LLM 编排 | LangGraph 1.2 + LangChain 1.3 | `retrieve -> answer` 两节点图 |
| LLM 抽象 | `langchain-openai` + `langchain-anthropic` + 工厂路由 | OpenAI/Anthropic 原生 + 5 家 OpenAI-compatible |
| Embedding | `httpx` 直连 `/v1/embeddings`，MiniMax 原生 body | OpenAI / MiniMax / 其他 OpenAI-compatible |
| 向量库 | ChromaDB（持久化到 `data/chroma/`） | cosine |
| 关系库 | SQLite + SQLModel + FTS5 全文索引 | `data/notes.db` |
| 文件解析 | pdfplumber、openpyxl、python-docx、python-pptx、pypdf、trafilatura、BeautifulSoup、pytesseract | 文本 / Office / PDF / OCR / URL |
| 飞书 | httpx + 官方 Open API | OAuth + DFS walk + bitable 记录 |
| 前端 | Vue 3 + Vite 6 + TypeScript | `<script setup>` + SFC |
| 状态管理 | Pinia 3 | chat / notes / sessions / models / settings |
| UI 库 | Naive UI 2.41 | HD 蓝色主题（`#3b82f6`） |
| 路由 | vue-router 4 | createWebHistory（path 模式） |
| SSE 解析 | 自写 `streamSse` | fetch + ReadableStream |
| 部署 | uvicorn 127.0.0.1:8001 + Vite 127.0.0.1:5174（仅本机） | `scripts/start-all.ps1` |

---

## 2. 核心功能清单

### 2.1 LLM 与模型管理

- **多 provider 路由**：OpenAI / Anthropic 原生 + DeepSeek / 智谱 / 月之暗面 / SiliconFlow / Ollama 走 OpenAI-compatible `base_url`（`backend/app/llm/factory.py`）
- **Auto 模式**：未指定 provider/model 时退回 `.env` 默认；用户 key 优先级 `header > body > .env`
- **每请求覆盖**：`base_url` / `api_key` / `provider` / `model` / `reasoning_level` 五个字段可临时覆盖
- **推理程度 4 档**：`low | medium | high | xhigh`，OpenAI / DeepSeek 走 `extra_body.reasoning_effort`；Anthropic 走 extended-thinking budget 映射
- **自动识别模型清单**：`POST /api/settings/custom-models` -> httpx 调 `<base_url>/models`，按 URL 关键字推断 provider
- **前端持久化**：localStorage 存自定义模型 + 选中模型 + 推理程度（`stores/models.ts`）

### 2.2 知识库入库

支持 11 种入口（`backend/app/tools/ingest.py`）：

| 入口 | 解析器 | 输出 |
|---|---|---|
| PDF 文本型 | `parse_pdf.py` (pdfplumber) | Markdown + 表格块 |
| PDF 扫描型 | `parse_pdf.py` (pdfplumber render + Tesseract OCR) | Markdown + 表格块 |
| DOCX | `parse_doc.py` (python-docx + 原生 XML) | Markdown + 表格块（保留合并） |
| PPTX | `parse_pptx.py` (python-pptx + 原生 XML) | Markdown + 表格块（保留合并） |
| XLSX | `parse_xlsx.py` (openpyxl) | Markdown + 表格块（保留合并） |
| CSV | `parse_csv.py` | Markdown 表格 |
| HTML | `parse_html.py` (BeautifulSoup / trafilatura) | Markdown |
| TXT / MD | 直读 | 原文 |
| 图片 | `ocr.py` (Tesseract `chi_sim`) | OCR 文本 |
| URL | `fetch_url.py` (trafilatura) | Markdown |
| 飞书文档 / 多维表格 | `parse_feishu_doc.py` | Markdown（见 §2.7） |

入库链路：`parse -> chunk_text(500/80) -> embed_texts -> Chroma add_chunks + FTS5 add_fts -> SQLite.embedded=true, chunk_count=N`。

### 2.3 表格识别（三层框架）新增

> 核心思想：**别找"一个全能的表格库"，把识别拆成「版面分析 -> 结构还原 -> 文字识别」三层，按文件类型决定在哪层发力**。

| 文件类型 | 走的层 | 实现 | 输出 |
|---|---|---|---|
| **XLSX / DOCX / PPTX** | 结构还原 | 直接吃 XML 语义：openpyxl `merged_cells.ranges`、DOCX `<w:tc gridSpan vMerge>`、PPTX `<a:tc gridSpan hMerge rowSpan vMerge>` | Markdown 表格，**零信息损失** |
| **CSV** | 结构还原 | 行解析 | Markdown 表格 |
| **PDF 文本型（含可见线条）** | 版面 + 结构 | pdfplumber `lines` 策略（边框切格）-> `text` 策略（空白聚类）fallback | Markdown 表格 + 跨页表头去重续接 |
| **PDF 文本型（纯空白对齐）** | 版面 | pdfplumber `text` 策略 + 垂直/水平策略调参 | Markdown 表格 |
| **PDF 扫描型** | 三层全走 | pdfplumber 渲染页 -> Tesseract PSM 12 -> 列对齐 + 行间距启发式聚成表格 | Markdown 表格（精度低于文本 PDF） |
| **飞书 docx** | 结构还原 | `parse_feishu_doc.py` raw_content 轻清洗 | Markdown |
| **飞书 bitable** | 结构还原 | `parse_feishu_doc.py` fields + records -> 表格（10 种 ui_type：Text/Number/Select/MultiSelect/DateTime/User/...） | Markdown 表格 |

**表格在 content 里以 Markdown 块输出**（`| col | col |\n|---|---|\n...`），下游 `chunk_text` 会把它们作为结构化块整体保留，LLM 看得到表头和列结构。

**接入更高精度扫描表格识别（可选扩展点）**：
- PaddleOCR PP-StructureV2（SLANet，中文友好）
- Azure Document Intelligence Layout（业界标杆）
- 合合 TextIn xParse（中文表格）
- 在 `backend/app/tools/parse_pdf.py` 替换 OCR 后处理即可，业务代码不动

**测试覆盖**：`scripts/table_tests/` 6 个 fixture + `run_all.py`，当前 **6/6 PASS**（xlsx / docx / pptx / pdf / 跨页 pdf / 扫描 pdf）。

### 2.4 RAG 检索与对话

**三层链路**（必须三层都 OK 才出引用卡片）：

| 层 | 文件 | 状态 | 关键逻辑 |
|---|---|---|---|
| 1. 入库 | `api/notes.py` + `storage/vector.py` + `storage/db.py` | OK | parse -> chunk -> embed -> Chroma + FTS5 |
| 2. 检索 | `api/chat.py` hybrid_search + `storage/hybrid.py` | OK | `0.7 * vec_score + 0.3 * kw_score`，top_k=5 |
| 3. prompt | `agent/nodes/answer.py` | OK | chunks -> system prompt，引用 `[n]` 标注 |

**检索细节**：
- 向量：Chroma cosine，distance -> 0~1 分
- 关键词：SQLite FTS5 BM25，**CJK 友好**：双 pass（phrase match + per-token OR + LIKE 兜底）
- **MiniMax 兼容**：embedding 先 `mode="query"`，上游拒（如 2013 invalid params）则自动 fallback 到 `mode="db"`
- 错误不再静默：原来 `except: pass` 改成 `logging.warning(...)`，`uvicorn.err.log` 能看到真实报错
- 阈值过滤：final_score < 0.18 或单维度 < 0.18 的 chunk 不进 prompt，避免「你叫什么名字」这种闲聊被强行附假引用

**SSE 事件流**（`backend/app/api/chat.py`）：
```
event: session       -> 新会话时推 session_id
event: stage         -> 阶段（rag_search / llm_stream / done）
event: citations     -> [{note_id, chunk_index, title, snippet, score}, ...]
event: message       -> 流式 token delta
data: [DONE]
```

**前端 UX**：
- 输入框顶部：知识库开关（`n-switch`）+ 模型选择器
- 输入框旁边：模型 + 推理等级下拉
- 流中：阶段标签（"检索知识库中..." -> "检索到 5 条（312ms）" -> "生成回答中..."）+ 已用秒数
- 答案下方：`CitationPreview` 卡片，列编号 / 标题 / chunk 索引 / score / 片段

### 2.5 会话管理

- `ChatSession` + `ChatMessage` 持久化（SQLModel）
- 标题自动取首条 user 消息前 50 字
- 无 `session_id` 时后端自动建会话，SSE `event: session` 推回，前端侧栏立即刷新（不等流结束）
- 侧栏搜索：标题 / 内容模糊匹配（前端 `ChatHistory.vue` 内）
- 会话独立：标题 + 预览 + 时间 + 消息数 + 删除按钮
- 删除会话同时清空消息（前端 `chat.clear()` + `router.push({name:'chat'})`）

### 2.6 设置与模型管理

- **设置页** (`SettingsView.vue`)：添加自定义 LLM entry（名称 / Base URL / API Key）-> 一键识别 -> 列表展示 -> 入库
- **每条 entry** 可设默认 chat 模型 + `embedding_model`（如 `embo-01` for MiniMax）
- **localStorage 隔离**：用户 key 不上传服务端，每次请求通过 `X-API-Key` header 透传
- **健康检查**：`GET /api/health` -> `{"status":"ok"}`

### 2.7 飞书知识库集成 新增

> 把飞书 wiki 空间里的文档 + 多维表格自动同步到本地 KB，走的入库链路与文件上传完全一致。

| 模块 | 文件 | 职责 |
|---|---|---|
| OAuth 客户端 | `tools/feishu_client.py` | tenant_access_token 缓存 2h，线程安全 |
| Wiki 节点 DFS | `tools/feishu_client.py` | `walk_nodes()` 递归所有子节点 |
| 文档解析 | `tools/parse_feishu_doc.py` | docx `raw_content` 轻清洗 + bitable records->Markdown |
| 同步编排 | `feishu_sync.py` | `sync_space()` / `sync_all()` / `SyncResult` 计数 |
| 路由 | `api/feishu.py` | `GET /status` / `GET /spaces` / `POST /sync` |
| 后台循环 | `main.py` startup | `FEISHU_SYNC_INTERVAL_MIN=15`（可设为 0 关掉） |

**支持的对象类型**：
- `docx`：拉 `raw_content` -> Markdown 入库（`source_type=feishu_docx`）
- `bitable`：拉 fields + records -> Markdown 表格入库（`source_type=feishu_bitable`），已处理 10 种 `ui_type`（Text/Number/Select/MultiSelect/DateTime/User/Checkbox/...）
- 其他（sheet/mindnote/...）：当前 skip

**去重**：以 `source_url` 为主键
- `feishu://wiki/{space_id}/{node_token}`
- `feishu://bitable/{app_token}/{table_id}`

第二次同步直接 `skipped`，不会重复入库。

**API**：
```
GET  /api/feishu/status         # 配置状态 + interval
GET  /api/feishu/spaces         # 列出可见 wiki 空间
POST /api/feishu/sync           # body 可选 {"space_id": "..."}，触发同步
```

**端到端验证通过**（用户真实数据）：
- 空间 `7676363835179207668` 「知识库」
- docx 「首页」（195 字）-> `source_type=feishu_docx`
- bitable 「任务管理」（10 字段 x 11 条记录，3260 字）-> `source_type=feishu_bitable`
- 第二轮同步 `synced=0 skipped=2 failed=0`，去重 OK

**安全注意**：飞书 App Secret 写在 `backend/.env`（已在 `.gitignore`），不要提交到 git；定期去 open.feishu.cn 重新生成。

### 2.8 前端 UX

- **HD 蓝色主题**：naive-ui `themeOverrides` 把 primary 改成 `#3b82f6`（默认绿色 -> 蓝色）
- **页面**：ChatView / NotesView / SettingsView（`vue-router` createWebHistory）
- **组件**：
  - `ChatHistory` — 侧栏：会话列表 + 搜索 + 新建 + 跳知识库
  - `MessageBubble` — 消息气泡（含思考过程折叠）
  - `CitationPreview` — 引用卡片
  - `ModelSelector` — 模型 + 推理等级（compact 80px 下拉）
  - `StreamingIndicator` — 流式阶段指示
- **Pinia stores**：chat / notes / sessions / models / settings
- **HTTP 客户端**：fetch + 自动 `X-API-Key` header + 自写 `streamSse`


### 2.9 部署（本地访问）

- 后端：`uvicorn 127.0.0.1:8001`（vite 已代理 `/api`）
- 前端：vite `host=127.0.0.1`、`allowedHosts=localhost/127.0.0.1`、`proxyTimeout 600000`（SSE 不被掐断）
- **访问入口**：仅本机 `http://127.0.0.1:5174`；不暴露公网（花生壳隧道已下线，对外访问恢复路径见 OPTIMIZATION.md §3 需先补 HTTPS + 鉴权）
- **一键启动**：`scripts/start-all.ps1`（杀旧 -> 起后端 -> 起前端 -> 探活）
- 上传限制：50MB（`HD_MAX_UPLOAD_BYTES` 可调）

### 2.10 多 Agent 编排（LangGraph + Router）新增

- **架构**：LangGraph StateGraph，入口走 Router 意图分类，按结果分支到 `retrieve` / `research` / `ingest` / `report`，前两者再进 `answer` 节点综合回答；环境变量 `HD_USE_GRAPH=false` 可一键回退旧直调链路。
- **4 个子 agent**：
  - **Router** (`agent/nodes/router.py`)：用便宜模型做意图分类 + query 改写，失败永远降级到 `chat`，不阻断主流程。配置：`HD_ROUTER_MODEL` / `HD_ROUTER_BASE_URL` / `HD_ROUTER_ENABLED`。
  - **研究 agent** (`agent/nodes/research.py`)：多轮 hybrid_search，最多 `HD_RESEARCH_MAX_ITER=3` 轮，每轮用便宜模型生成下一个检索角度，凑够 `HD_RESEARCH_TARGET_CHUNKS=8` 提前停。
  - **入库管家** (`agent/nodes/ingest.py`)：检测 URL / 触发词，调用现有 `ingest_url` / `ingest_text`；再用便宜模型提取标题 / 3-5 个标签 / 一句话摘要；FTS5 软查重，返回结构化结果给前端 `IngestResultCard`。
  - **周报 agent** (`agent/nodes/report.py`)：拉取最近 N 天笔记（默认 7 天，可识别"上个月" / "近 30 天"等中文表达），按 tag 分组，LLM 生成 Markdown 周报，存为新 note。
- **State 扩展**：新增 `intent` / `rewritten_query` / `research_iterations` / `research_notes` / `ingest_result` / `report_result` 字段。
- **SSE 事件**（前端 StreamingIndicator 已适配）：
  - `event: stage` 新增 `stage: "router"` + `stage: "agent"` + 字段 `intent` / `agent` / `iterations`
  - `event: ingest` + `event: report` 携带结构化结果

### 2.11 飞书增量同步 升级

- Note 表加 `source_revision` + `source_updated_at` 字段；启动时 `_migrate_notes` 自动加列，老数据 NULL 视为未知。
- 同步对比 Feishu `obj_edit_time`：相同 → `skipped`；不同 → 删除旧 chunks (Chroma + FTS5) → 重走入库链路 → 更新 revision。Note id 保持不变，引用不会失效。
- `POST /api/feishu/sync` body 支持 `force_full=true` 全量重抓。

### 2.12 RAG Eval

- `scripts/rag_eval/golden.jsonl`：6 条 golden 样例（精确事实 / 多跳综合 / 追问改写 / 应拒绝的闲聊）。
- `scripts/rag_eval/run.py`：直连 `hybrid_search`，输出 Markdown 报告含 Recall@K / MRR / 闲聊误命中率，按类别分组 + per-case 表格。支持 `--top-k` / `--out` 参数。

---

## 3. 系统架构

```
+----------------------+      SSE      +-----------------------+
|  Vue 3 + naive-ui    | <-----------> |   FastAPI (8001)     |
|  Chat / Notes /      |  REST / SSE   |   - chat (SSE+RAG)    |
|  Settings            |               |   - notes (ingest)    |
+----------------------+               |   - search            |
                                       |   - sessions          |
                                       |   - settings          |
                                       |   - feishu            |
                                       +----------+------------+
                                                  |
                                                  v
                                       +-----------------------+
                                       |   LangGraph           |
                                       |   retrieve -> answer  |
                                       +----+--------------+----+
                                            |              |
                          +-----------------+              +-----------------+
                          v                                               v
              +------------+----------+                      +-----------+-----------+
              |   Hybrid Search       |                      |   LLM (factory)      |
              |   0.7 * vec + 0.3*kw  |                      |   7 providers        |
              +----+----+-------------+                      +-----------+-----------+
                   |    |                                            |
                   v    v                                            v
            +------+    +------+                            +---------+---------+
            |Chroma|    | FTS5 |                            | OpenAI / Anthropic|
            +------+    +------+                            | DeepSeek / Zhipu  |
                                                            | Moonshot / Olla   |
                                                            | SiliconFlow / ... |
                                                            +-------------------+
```

---

## 4. 数据流（RAG 三层）

### 入库

```
PDF/DOCX/PPTX/XLSX/CSV/HTML/TXT/图片/URL/飞书docx/飞书bitable
    -> parse_*  -> {title, content}  (content 内表格以 Markdown 块存在)
    -> chunk_text(500/80)
    -> embed_texts (OpenAI-compat / MiniMax native)
    -> Chroma.add + SQLite FTS5.add
    -> Note {embedded=True, chunk_count=N}
```

### 检索 + 问答

```
ChatView -> chat.send() -> chatStream() (api/chat.ts) -> POST /api/chat (SSE)
   |
   v
api/chat.py:  use_rag=True?
   -> hybrid_search(query, top_k=5, embedding_model, embedding_base_url, api_key)
        -> embed_texts(query)              [OpenAI-compat]
        -> vector_search(emb, top_k=10)    [Chroma cosine]
        -> fts_search(query, top_k=10)     [SQLite FTS5 BM25, CJK 双 pass]
        -> merge + dedupe by (note_id#chunk_index)
        -> score = 0.7 * vec + 0.3 * kw
        -> 阈值过滤 (min_score=0.18, min_dim_score=0.18)
        -> trim top_k
   -> graph.stream(initial_state)
        -> retrieve_node  -> answer_node
   -> answer_node: build_prompt(messages + chunks) -> LLM stream
   -> SSE: session -> stage(rag_search started/done) -> message delta -> citations -> done
   -> 前端 stream 累加 + stripThink + 渲染 + CitationPreview
```

---

## 5. API 端点表

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | SSE 聊天（含 RAG） |
| POST | `/api/search` | 独立 hybrid 搜索（无需 LLM） |
| GET / POST / DELETE | `/api/notes` | 笔记 CRUD |
| POST | `/api/notes/file` | 文件上传入库（任意 11 种类型） |
| POST | `/api/notes/image` | 图片 OCR 入库 |
| POST | `/api/notes/text` | 文本入库 |
| POST | `/api/notes/url` | URL 抓取入库 |
| POST | `/api/notes/{id}/download` | 下载磁盘 .md |
| POST | `/api/notes/{id}/reembed` | 重新跑 embedding |
| GET | `/api/notes-stats` | 笔记 + Chroma 计数 |
| GET | `/api/sessions` | 会话列表 |
| POST | `/api/sessions` | 新建会话 |
| GET | `/api/sessions/{id}` | 会话详情 |
| DELETE | `/api/sessions/{id}` | 删会话 |
| GET / POST | `/api/settings/models` | 列出 / 写模型配置 |
| POST | `/api/settings/custom-models` | httpx 探测 `<base_url>/models` |
| GET | `/api/feishu/status` | 飞书配置状态 |
| GET | `/api/feishu/spaces` | 列出可见 wiki 空间 |
| POST | `/api/feishu/sync` | 触发同步（可选 `space_id`） |

---

## 6. 目录结构（当前真实结构）

```
one_agent/
|-- docs/
|   |-- PLAN.md                # 项目计划书（P0-P9）
|   |-- RAG.md                 # RAG 三层链路详解
|   |-- SKILLS.md              # Skill 中心（v0.4）
|   |-- FEATURES.md            # ★ 本文档：功能现状总览
|   \-- file-writing-policy.md # UTF-8 无 BOM 写入规范
|-- backend/
|   \-- app/
|       |-- main.py            # FastAPI 入口 + 中间件 + Feishu 后台循环
|       |-- config.py          # pydantic-settings（含 7 个 feishu_* 字段）
|       |-- feishu_sync.py     # 飞书同步编排
|       |-- api/               # 9 个 REST 路由
|       |   |-- chat.py  notes.py  search.py  sessions.py
|       |   |-- settings.py  custom_models.py  health.py
|       |   \-- feishu.py
|       |-- agent/             # LangGraph
|       |   |-- graph.py       # router -> (retrieve|research|ingest|report) -> answer
|       |   |-- state.py
|       |   |-- schemas.py
|       |   |-- prompts/
|       |   \-- nodes/
|       |       |-- router.py      # 便宜模型 intent 分类 + query 改写
|       |       |-- retrieve.py    # hybrid_search 包装 (优先 rewritten_query)
|       |       |-- research.py    # 多轮 hybrid_search + follow-up 生成
|       |       |-- ingest.py      # URL/文本检测 + LLM 元数据 + FTS5 软查重
|       |       |-- report.py      # 时间窗拉取 + 按 tag 分组 + LLM 周报
|       |       \-- answer.py      # ANSWER_INSTRUCTIONS + citations 收集
|       |-- embeddings/factory.py   # OpenAI-compat + MiniMax 原生 body
|       |-- llm/factory.py          # 7 provider + reasoning + base_url override
|       |-- storage/
|       |   |-- db.py          # SQLModel + FTS5 + ChatSession/ChatMessage
|       |   |-- vector.py      # Chroma collection 封装
|       |   \-- hybrid.py      # 向量 0.7 + FTS5 0.3 加权
|       \-- tools/             # 11 个解析器 + ingest + ocr + feishu
|           |-- chunk.py  fetch_url.py  ocr.py  ingest.py
|           |-- parse_pdf.py  parse_doc.py  parse_pptx.py  parse_xlsx.py
|           |-- parse_csv.py  parse_html.py
|           |-- parse_feishu_doc.py
|           |-- feishu_client.py
|           \-- parse_*        # （按文件类型）
|-- frontend/
|   \-- src/
|       |-- main.ts  App.vue  style.css  router/index.ts
|       |-- api/       # client.ts + chat/notes/sessions/settings/custom-models.ts
|       |-- stores/    # chat / notes / sessions / models / settings (Pinia)
|       |-- views/     # ChatView / NotesView / SettingsView
|       \-- components/   # ChatHistory / MessageBubble / CitationPreview
|                          # / ModelSelector / StreamingIndicator
|-- scripts/
|   |-- start-all.ps1         # 一键启动（杀旧 -> 起后端 -> 起前端 -> 探活，本地访问）
|   |-- install-service.ps1   # NSSM 安装 backend 为 Windows 服务（按需启用）
|   |-- backup.ps1            # SQLite VACUUM INTO + robocopy + 14 份轮转
|   |-- _start_vite.ps1
|   |-- feishu_ws.py          # 飞书 web socket（备选，本项目未启用）
|   |-- start_feishu_ws.ps1
|   |-- rag_eval/             # RAG 评测套件
|   |   |-- golden.jsonl      # 6 条 golden 样例
|   |   \-- run.py            # runner (Recall@K / MRR / 闲聊误命中率)
|   \-- table_tests/          # 表格识别测试套件（6/6 PASS）
|       |-- run_all.py
|       |-- make_fixtures.py  make_continued.py  make_scanned.py
|       |-- sample.xlsx / .docx / .pptx / .pdf
|       \-- sample_continued.pdf / sample_scanned.pdf
\-- logs/                     # uvicorn.out.log / uvicorn.err.log（启动后生成）
```

---

## 7. 启动 & 自检

### 7.1 一键启动

```powershell
D:\one_agent\scripts\start-all.ps1
```

### 7.2 手动启动

```powershell
# 后端
cd D:\one_agent\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# 前端（新 shell）
cd D:\one_agent\frontend
npm install
npm run dev                   # http://127.0.0.1:5174
```

### 7.3 表格识别自检（无需浏览器）

```powershell
cd D:\one_agent\scripts\table_tests
$env:PATH += ";C:\Program Files\Tesseract-OCR"     # OCR fallback 用
D:\one_agent\backend\.venv\Scripts\python.exe run_all.py
```

**当前基线：6/6 PASS**（xlsx / docx / pptx / pdf / 跨页 pdf / 扫描 pdf）。

### 7.4 RAG 自检（无需浏览器）

```powershell
cd D:\one_agent\backend
.\.venv\Scripts\python.exe -c "from app.storage.hybrid import hybrid_search; print(hybrid_search('牛魔王的来历', top_k=3, base_url='https://api.minimax.chat/v1', api_key='<key>', model='embo-01'))"
```

应返回 >= 1 条 chunk；若空，看 `uvicorn.err.log` 末尾的 `hybrid_search embed failed` / `hybrid_search fts failed`。

### 7.5 飞书自检

```powershell
# 配置：backend/.env 加 FEISHU_ENABLED=true + FEISHU_APP_ID + FEISHU_APP_SECRET
curl http://127.0.0.1:8001/api/feishu/status
curl http://127.0.0.1:8001/api/feishu/spaces
curl -X POST http://127.0.0.1:8001/api/feishu/sync
```

---

## 8. 已知约束 / 注意事项

1. **embedding 模型必须和入库时一致**：换 embedding 后旧的 Chroma 向量会失效，要用「重跑 embedding」按钮重建
2. **PowerShell UTF-8 BOM**：`docs/file-writing-policy.md` 是踩坑记录，写 `.py / .vue / .ts / .css / .html / .md / .json` 必须用 `[System.Text.UTF8Encoding]::new($false)`，否则 parser 会报 invalid character
3. **RAG 阈值**：`min_final_score=0.18`、`min_dim_score=0.18`，低于则不进 prompt（避免闲聊被强行附假引用）；改 `storage/hybrid.py` 顶部常量
4. **MiniMax embedding**：必须显式传 `mode="db"`（存储）/ `mode="query"`（检索），否则会拿到 2013 invalid params；factory 已自动 fallback
6. **飞书 App Secret**：已写到 `backend/.env`（在 `.gitignore`），建议定期去 open.feishu.cn 重新生成
8. **上传大小限制**：默认 50MB，`HD_MAX_UPLOAD_BYTES` 环境变量可调
9. **OCR 依赖**：Tesseract（`chi_sim.traineddata` 需单独装），`ocr.py` 启动时会自动检测并提示

---

## 9. 路线图（PLAN.md P0-P9 当前进度）

| 阶段 | 内容 | 状态 | 备注 |
|---|---|---|---|
| **P0** | 计划书 | OK | `docs/PLAN.md` |
| **P1** | 后端骨架 | OK | FastAPI + LangGraph 空图 + 模型工厂 |
| **P2** | 入库链路 | OK | URL / text / 11 种文件格式 + 飞书 |
| **P3** | 检索 + 问答 | OK | 向量 + 关键词混合 + 引用卡片 |
| **P4** | Agent 化 | 部分 | 当前仅 `retrieve -> answer`，intent_router 未启用 |
| **P5** | 前端骨架 | OK | Vue 3 + Pinia + Naive UI |
| **P6** | 端到端 | OK | SSE / 引用卡片 / 入库对话框 |
| **P7** | 多模型切换 | OK | + Auto + 自定义 base_url + 推理 4 档 |
| **P8** | 体验打磨 | OK | 主题色 / 侧栏搜索 / 流式阶段 |
| **P9** | 高级 | 部分 | OK OCR / OK 多格式入库 / OK 飞书 / 缺 RSS / 缺 周报 / 缺 MCP |

**已完成的高级能力**：表格识别三层框架、飞书知识库同步（花生壳公网隧道已下线）。

**未做的（可选下一步）**：
- WebSocket / SSE 推送飞书同步进度（当前只能同步完后看日志）
- 飞书增量同步（当前以 `source_url` 跳过已有，文档改了不会重抓——需要存 revision/etag 做内容比对）
- 飞书清空 / 撤销同步 API
- 飞书凭证写入 CLI（`python -m app.feishu_setup`）
- 接入 PaddleOCR PP-StructureV2 提升扫描 PDF 表格识别精度
- Skill 后端接入（`/api/skills/*`）+ 持久化
- RSS 定时抓取 + 周报推送

---

## 10. 相关文档索引

- `docs/PLAN.md` — 项目原始计划书（P0-P9 路线图 + 技术选型）
- `docs/RAG.md` — RAG 三层链路详解（含 CJK 查询修复记录）
- `docs/SKILLS.md` — Skill 中心（前端推荐 / 我的 Skill）
- `docs/file-writing-policy.md` — UTF-8 无 BOM 写入规范（踩坑记录）
- `README.md` — 项目 README + 表格识别章节
