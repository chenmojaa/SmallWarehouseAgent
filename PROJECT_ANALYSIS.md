# 个人知识小助手 —— Agent 项目技术分析文档

> 本文档全面梳理项目的功能实现与技术方案，可直接作为简历项目的素材来源。

---

## 一、项目概览

**个人知识小助手** 是一个全栈 AI Agent 应用：用户通过自然语言对话，系统自动完成意图识别、知识检索、多轮研究、知识入库、周报生成等任务，并将答案连同可点击的引用来源一起流式返回。

- **后端**：Python 3.11+ / FastAPI / LangGraph / LangChain / SQLite (SQLModel) / ChromaDB / FTS5
- **前端**：Vue 3 / TypeScript / Pinia / Vue Router / Naive UI / marked + DOMPurify + mermaid
- **通信**：REST + SSE（Server-Sent Events）流式传输
- **大模型**：支持 OpenAI / Anthropic / MiniMax 等多 Provider 可切换（含 reasoning 模型）

### 核心架构图（文字版）

```
用户提问
   │
   ▼
┌─────────────────────────── LangGraph 状态机 ───────────────────────────┐
│                                                                        │
│  router ──┬─ chat        → retrieve（混合检索）→ END（chat.py 流式作答）│
│           ├─ chat_no_rag → END（寒暄快速通道，跳过检索）                │
│           ├─ research    → research（多轮研究循环）→ END                │
│           ├─ ingest      → ingest（文档解析入库）→ END                  │
│           └─ report      → report（周报生成）→ END                      │
│                                                                        │
│  Checkpointer: AsyncSqliteSaver（data/checkpoints.sqlite，重启不丢状态）│
└────────────────────────────────────────────────────────────────────────┘
   │
   ▼
SSE 流式返回（stage 进度 / think 思考过程 / delta 正文 / citations 引用）
```

---

## 二、后端功能与实现方式

### 2.1 Agent 核心：LangGraph 状态机编排

**文件**：`backend/app/agent/graph.py`、`state.py`

- 使用 **LangGraph StateGraph** 构建 5 节点工作流：`router → retrieve / research / ingest / report`，通过 `add_conditional_edges` 按 `route_by_intent` 分发。
- 状态用 `TypedDict`（`AgentState`）定义，包含会话消息、用户画像、历史摘要、意图、改写查询、检索分块、引用等 20+ 字段。
- **关键设计决策**：`messages` 字段不使用 `operator.add` reducer——因为服务端每次从 DB 播种完整历史（服务端为唯一事实源），若用累加语义会与 checkpoint 历史叠加导致消息重复。
- **Checkpointer 持久化**：`AsyncSqliteSaver` 落盘至 `data/checkpoints.sqlite`，进程重启后对话状态不丢失。由于 saver 构造依赖运行中的事件循环，采用**惰性异步单例**模式在首次请求时构建并缓存。

### 2.2 意图路由节点（Router）

**文件**：`backend/app/agent/nodes/router.py`

- **正则快速通道**：对「你好 / hi / 谢谢 / 你是谁」等寒暄意图直接正则匹配，绕过 LLM 分类（此前用 MiniMax 做分类产生 12s 延迟，改为正则后毫秒级响应）。
- **LLM 路由**：输出意图（chat / research / ingest / report）+ **查询改写** `rewritten_query`（结合最近 3 轮历史消解指代，如「它」→ 具体实体）。
- **踩坑经验**：结构化输出（structured output）会被 reasoning 模型的 `<think>` 包裹破坏，因此改为**原始 JSON 文本解析**，容错更强。
- 提示词中约束改写查询「与用户最新消息保持同一语言」，避免改写成英文导致中文检索失效。

### 2.3 混合检索（Hybrid Retrieval）

**文件**：`backend/app/storage/hybrid.py`、`vector.py`、`db.py`

- **双路召回**：
  - **向量检索**：ChromaDB，`cosine` 相似度 + HNSW 索引，本地持久化于 `backend/data/chroma/`；
  - **关键词检索**：SQLite **FTS5** 全文索引（`chunk_fts` 虚拟表，unicode61 tokenizer），弥补向量检索对「牛魔王」等 CJK 专有名词的弱点。
- **融合排序**：`final = 0.7 × 向量分 + 0.3 × 关键词分`，并设最终分数与维度分数双阈值过滤。
- **Embedding**：MiniMax `embo-01` API，文档入库用 `db` 模式、用户查询用 `query` 模式（同模型不同模式保证向量空间一致性），按 32 条/批批量请求。
- Embedding API Key 缺失时自动降级为纯 FTS5 检索，保证服务可用。

### 2.4 文档解析与分块（Ingest）

**文件**：`backend/app/agent/nodes/ingest.py`、`backend/app/rag/chunk.py`

- 支持多种来源：**飞书文档、网页（trafilatura 抓取）、纯文本、上传文件**（docx / pptx / xlsx / PDF，PDF 用 pypdf + pdfplumber 双引擎，含 pytesseract OCR 兜底）。
- **分块策略**：500 字符窗口 + 80 字符重叠，优先在段落边界切分，其次句子边界——平衡召回粒度与上下文完整性。
- 入库时对内容做 **Unicode 转义序列解码**（修复 Excel 来源标题乱码问题）。
- Ingest 节点由 LLM 自动生成标题、标签、摘要，支持重复检测（duplicate_of）。

### 2.5 多轮研究代理（Research Agent）

**文件**：`backend/app/agent/nodes/research.py`

- 面对复杂问题执行**多轮检索循环**：每轮基于已有发现生成后续查询（`research_notes` 记录中间查询，`research_iterations` 计数），直至信息充分。
- 修复过占位符 bug（`<<ORIG` 少了 `>>` 导致原始问题从未注入后续提示词），现通过 `<<ORIG>>` 确保每轮都锚定用户原问题。

### 2.6 流式作答与引用（Answer）

**文件**：`backend/app/api/chat.py`、`backend/app/agent/nodes/answer.py`

- **SSE 事件分级推送**：`stage`（router/rag/agent/llm_stream 各阶段进度）→ `delta`（正文增量）→ `citations`（引用列表）→ `done`，前端可展示全流程进度条。
- **上下文组装固定顺序**：system（人设 + 历史摘要 + 用户画像 + 参考材料）→ 对话历史 → 当前问题。
- **Token 预算控制**：参考材料总预算 3000 tokens（低分块先截断），单块硬上限 800 字符。
- **历史滑动窗口**：最近 12 条消息 / 2000 tokens，窗口外内容压缩为 ≤150 字摘要注入 system。
- **引用系统**：提示词要求 LLM 在正文中插入 `[n]` 标记；后端按 index 排序 citations 保证与前端按钮映射正确；正则提取引用（已知对 LLM 格式波动敏感，是待改进点）。
- **提示词工程**：人设「个人知识小助手」；语言约束（与提问同语言）；空参考兜底（无参考资料时用自身知识回答且绝不提参考材料）。

### 2.7 用户认证（Auth）

**文件**：`backend/app/api/auth.py`

- **注册/登录**：手机号 + 密码，`users` 表存储 `password_salt` + PBKDF2 哈希（**不存明文**），phone 唯一索引。
- **Token 机制**：自签格式 `userId.exp.HMAC签名`，密钥持久化于 `backend/data/auth_secret` 文件（重启不掉线），TTL 7 天。
- API：`/register`、`/login`、`/change-password`、`/me`（服务端验签）。
- 中间件自动将请求中的 X-API-Key 持久化到服务端（解决 Embedding Key 首次配置问题）。

### 2.8 飞书知识库同步

**文件**：`backend/app/feishu_sync.py`

- 基于 `obj_edit_time` 的**增量同步**：仅拉取上次同步后变更的文档。
- **失败重试机制**（关键修复）：初始同步时 Embedding 失败（缺 API Key）的文档曾因 revision 已推进而被永久跳过（「待索引」状态）。修复为：跳过条件改为「revision 匹配 **且** embedded=True」，且**仅在 embedding 成功后才推进 revision**，未索引文档每轮自动重试。

### 2.9 技能系统（Skills）

**文件**：`backend/app/api/skills.py`

- 支持上传**文件夹或 zip 压缩包**，后端统一处理：
  - **安全校验**：限制压缩包大小、文件数、路径穿越（zip slip）防护；
  - 自动解压，要求根目录含 `SKILL.md` 才视为合法技能；
  - 注册写入 `installed.json`，支持查看技能文件结构、打包下载 zip。
- 技能中心分「推荐首页」与「我的技能」两个视图，支持搜索、介绍展开/收起。

### 2.10 MCP 服务管理与工具调用

**文件**：`backend/app/api/mcp.py`、`backend/app/agent/tools/mcp_client.py`、`mcp_tools.py`

- **配置管理**：MCP 服务 CRUD，支持 stdio / http（SSE / Streamable HTTP）两种传输方式，启动参数与环境变量 JSON 配置，连接测试，内置预设一键导入。
- **Agent 真实调用 MCP（全链路已打通）**：
  - **自研轻量 MCP 客户端**（不依赖 `mcp`/`langchain-mcp-adapters`）：子进程拉起 stdio server → JSON-RPC 2.0 握手（initialize）→ `tools/list` 工具发现 → `tools/call` 工具执行；
  - **协议细节**：MCP stdio 传输为**换行分隔 JSON**（非 LSP Content-Length 帧）；Windows 下用**每进程单例读线程 + queue** 读取（`select()` 不支持 Windows 管道，且多读线程会互抢响应行）；`npx` 需解析为 `npx.CMD`；进程清理用 `taskkill /T` 杀整棵进程树（terminate 只杀 cmd 壳会留下 node 僵尸）；
  - **工具抽象**：暴露 `mcp_list_servers` / `mcp_discover_tools` / `mcp_invoke` 三个聚合工具（而非每工具一个），模型先发现再调用；能力清单注入 system prompt；
  - **tool-call 循环**：answer 节点 `bind_tools` 后最多 4 步循环（可配），每次调用的发起/结果通过 SSE `tool` 事件推给前端，渲染为 running→ok/failed 状态 chips。

### 2.11 周报代理（Report）

**文件**：`backend/app/agent/nodes/report.py`

- 拉取最近 N 天笔记 → 按标签分组 → LLM 汇总生成结构化周报 → **周报本身再作为一条笔记入库**，形成知识闭环。

### 2.12 提示词与配置管理

- 提示词外置于 `config.yaml`，支持多模型配置；
- 基于 **mtime 的提示词缓存自动失效**（`__init__.py`），改提示词无需重启后端；
- 每请求级参数覆盖（provider / model / base_url / api_key / reasoning_level / embedding_model override），支持运行时切换模型。

---

## 三、前端功能与实现方式

### 3.1 整体架构

- **Vue 3 组合式 API + TypeScript + Pinia + Vue Router + Naive UI**，Vite 构建（HMR 热更新）。
- 页面：登录页 `/login`、聊天 `/chat`（含会话 ID 路由）、知识库 `/notes`、设置 `/settings`、MCP 管理 `/mcp`。
- **明暗主题**：CSS 变量体系（`--bg-app` / `--brand-blue` / `--text-primary` 等），组件统一引用变量实现一键换肤。

### 3.2 SSE 流式传输

**文件**：`frontend/src/api/client.ts`、`chat.ts`

- `streamSse()` 基于 fetch POST 流式读取，手动按 `event:` / `data:` / 空行解析 SSE 协议（EventSource 不支持 POST 的替代方案）。
- 将后端事件映射为 `session / delta / citations / stage / error / ingest / report / done` 前端事件。

### 3.3 思考过程（Thinking）流式展示

**文件**：`frontend/src/stores/chat.ts`

- 流式期间维护 `visible` / `thinkBuf` / `inThink` 三个缓冲区，实时从 delta 中分离 `<think>...</think>` 内容，思考过程**全程流式可见**（默认折叠，可展开）。
- **踩坑修复**：
  - `'</think>'` 偏移 bug（close 标签 8 字符曾被 +9，吃掉答案首字）；
  - reasoning 模型流式输出偶尔不闭合 `</think>`，正则改为**闭合标签可选**，保证未闭合时也能提取已有思考内容；
  - 渲染条件改为「只要有内容（含未完成思考块）就渲染气泡」，修复首次不显示、切页返回才显示的问题。

### 3.4 消息渲染（MessageBubble）

**文件**：`frontend/src/components/MessageBubble.vue`

- **三级解析**：`splitThink()` 提取思考块 → `splitSourceLine()` 提取尾部「来源：[n]」→ 正文 Markdown 渲染。
- **Markdown 渲染管线**：`marked` 渲染 + 自定义 code renderer 保留 mermaid 源码 → **DOMPurify 消毒防 XSS** → mermaid 异步渲染图表。
- **行内引用交互**：正文中 `[n]` 替换为带 `data-cite` 的可点击徽章（事件委托），点击高亮对应来源卡片。
- 思考区块展开状态持久化到 localStorage。

### 3.5 引用来源预览（CitationPreview）

- 展示 `[index]` + 标题 + 来源类型标签（飞书文档 / 网页 / 文本 / 上传文件）+ chunk/score + 摘要片段；
- 前端对 LLM 返回的 `\uXXXX` 转义标题/摘要做解码显示（配合后端入库解码，双保险）。

### 3.6 消息操作（复制 / 重新生成 / 删除 / 回退）

**文件**：`frontend/src/views/ChatView.vue`、`stores/chat.ts`

- hover 消息卡片显示操作栏：时间戳 + 复制 + 重新生成（仅助手消息）+ 删除 + 回退；
- 用户消息操作栏右对齐、助手消息左对齐（role class + flex 方向控制）；
- 点击反馈：蓝色高亮 + 0.35s 缩放动画（1→1.25→1）+ 0.8s 自动恢复；
- store 实现 `deleteMessage` / `regenerate` / `undoLast` 三个 action。

### 3.7 登录与路由守卫（安全修复）

**文件**：`frontend/src/router/index.ts`、`stores/auth.ts`

- **问题**：原守卫只查 localStorage 是否有 token 字符串，复制 URL 即可绕过登录。
- **修复后的三层校验**：
  1. 本地解析 token `userId.exp.签名` 中的 exp 检查过期；
  2. 调用 `/api/auth/me` 服务端验证 HMAC 签名真实性；
  3. 每次页面加载仅校验一次（内存缓存），登录/登出/401 时联动重置缓存与登录态。
- 未登录访问受保护路由 → 跳转 `/login`；已登录访问登录页 → 重定向 `/chat`。

### 3.8 知识库页面（NotesView）

- 本地知识库列表（标题/摘要搜索、Unicode 解码显示）、统计信息、飞书空间选择与手动同步触发。

### 3.9 MCP 管理页面（McpView）

- 三段式卡片编辑器：基本信息 → 传输方式（stdio/http 大按钮切换，选中蓝色高亮）→ 高级配置（参数/环境变量用等宽字体编辑）；
- JSON 格式前端校验、连接测试、预设一键导入、删除确认。

---

## 四、数据库设计

SQLite：`backend/data/notes.db`

| 表 | 用途 |
|---|---|
| `users` | 用户（phone 唯一索引、password_salt、PBKDF2 password_hash、时间戳） |
| `notes` | 知识条目（标题、标签、摘要、来源类型、飞书 revision、embedded 状态） |
| `chunks` / `chunk_fts` | 文本分块 + FTS5 全文索引虚拟表 |
| 会话/消息表 | 聊天会话与消息持久化（服务端为事实源，每次请求重新播种历史） |

另有两个独立持久化文件：
- `data/checkpoints.sqlite`：LangGraph AsyncSqliteSaver 状态检查点；
- `data/chroma/`：ChromaDB 向量库（cosine + HNSW）；
- `data/auth_secret`：token 签名密钥。

---

## 五、技术亮点总结（简历可直接引用）

1. **基于 LangGraph 的多 Agent 编排**：router / retrieve / research / ingest / report 五节点状态机 + 条件边分发，AsyncSqliteSaver 持久化 checkpoint 保证重启不丢对话状态；深入理解 reducer 语义（避免 operator.add 与持久化 checkpoint 的消息叠加问题）。
2. **混合检索（Hybrid Search）**：0.7×向量（ChromaDB cosine + HNSW）+ 0.3×FTS5 关键词融合排序，解决纯向量检索对中文专名召回差的问题；db/query 双模式 embedding 保证向量空间一致。
3. **全链路 SSE 流式体验**：分级事件（stage 进度/思考过程/正文增量/引用），前端手写 SSE 解析器 + 三缓冲区思考分离算法，实现 reasoning 模型思考过程全程流式可见。
4. **RAG 工程化细节**：500 字/80 重叠的边界感知分块、3000 token 参考预算 + 低分先截断、12 条滑动窗口 + 历史压缩摘要、行内 [n] 引用标记与来源卡片联动。
5. **多轮研究代理**：迭代式检索-生成循环，research_notes 追踪中间查询，每轮锚定原始问题。
6. **安全实践**：PBKDF2 密码哈希、HMAC 自签 token + 前端三层登录校验（本地过期 + 服务端验签 + 缓存联动）、DOMPurify 防 XSS、zip 路径穿越防护。
7. **生产级容错**：embedding 失败重试（revision 只在成功后推进）、embedding 缺 key 自动降级 FTS5、提示词 mtime 缓存失效（改词不重启）、LLM 输出容错解析（think 包裹的 JSON）。
8. **性能优化**：正则快速通道替代 LLM 意图分类（12s → 毫秒级）、embedding 批量请求（32/批）、惰性单例构建异步资源。
9. **完整产品闭环**：登录注册 → 多源知识入库（飞书增量同步/网页/文件）→ 检索问答 → 周报自动生成再入库，形成知识管理闭环。

---

## 六、可量化指标（简历数字素材）

- 5 个 Agent 节点、4 类意图路由、1 条寒暄快速通道
- 混合检索权重 0.7 / 0.3，双阈值过滤
- 分块 500 字符 / 80 重叠；参考预算 3000 tokens；单块上限 800 字符
- 历史窗口 12 条 / 2000 tokens，溢出压缩 ≤150 字
- Embedding 批量 32 条/请求；token TTL 7 天
- 意图分类延迟从 ~12s 优化到毫秒级（正则快速通道）

---

## 七、已知局限与改进方向（面试可谈）

- 引用提取依赖正则，对 LLM 输出格式波动敏感 → 可改用结构化输出或函数调用
- Research 代理缺少进度流式推送，用户体验偏黑盒
- FTS5 unicode61 对中文分词不理想 → 可换 jieba 分词 + 自定义 tokenizer
- localStorage 存 token 有 XSS 窃取风险 → 可升级 httpOnly cookie + CSRF 防护
