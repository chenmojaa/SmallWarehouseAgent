<p align="center"><a href="README.md"><img src="https://img.shields.io/badge/lang-English-blue.svg" alt="English"></a>&nbsp;<a href="README.zh.md"><img src="https://img.shields.io/badge/lang-%E4%B8%AD%E6%96%87-red.svg" alt="??"></a></p>

<div align="center">

# HD — 个人知识库助手

**本地优先的“第二大脑”，把零散的资料变成可检索的知识库，支持表格感知 OCR、多智能体 RAG 和飞书知识库同步。**

</div>

<div align="center">

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![Vue 3](https://img.shields.io/badge/vue-3-42b883.svg)](https://vuejs.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#-license)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Chroma](https://img.shields.io/badge/vector-Chroma-ff6f00.svg)](https://www.trychroma.com)

[功能](#功能) · [快速开始](#快速开始) · [架构](#架构) · [文档](docs/FEATURES.md)

</div>

---

## 这是什么？

HD 是一个跑在你本机上的个人知识库，配套一个聊天界面——能拿你自己的文档回答问题，每条结论都带 `[1] [2]` 引用，点回去就能看到原文片段。

一开始只是个 RAG 演示，后来演化成多智能体系统：

- **路由器**先搞清楚你的需求是聊天、多轮研究、入库还是周报
- 四个**子智能体**分别干活
- 最后由 LLM 综合答案，带可点击的引用回到原始切片

它和别的 RAG 不一样的几个点（一句话版）：

- **表格感知解析**——Excel / Word / PPT 的合并单元格完整保留，扫描 PDF 走 OCR + 列聚类还原表格；出来的全是 LLM 能直接读的 Markdown 表格。
- **混合检索**——Chroma 向量 + SQLite FTS5 BM25（按 `0.7 / 0.3` 加权），中文友好，首请求不会因为 `embo-01` 的怪脸气炸掉。
- **多智能体 LangGraph**——路由器 -> (研究 | 入库 | 周报)，配 `HD_USE_GRAPH=false` 兑底直调链路。
- **飞书知识库同步**——文档 + 多维表格拉进同一个 KB，按 `obj_edit_time` 增量更新，没改的页面不重拉。
- **评测驱动**——`scripts/rag_eval/` 内置金标准集和跑分脚本，出 Recall@K / MRR / 闲聊误引率。调权重、重跑、拍板。

---

## 功能

### 入库 — 11 条路径

| 格式 | 解析器 | 说明 |
|---|---|---|
| PDF（文本型） | pdfplumber | 行对文本策略；跨页标题去重 |
| PDF（扫描型） | pdfplumber 渲染 + Tesseract OCR | 列聚类 + 行间距含义；中文需要 `chi_sim.traineddata` |
| DOCX | python-docx + 原始 XML | 直接走 `gridSpan` / `vMerge`，绕过 `_Cell` 池化 |
| PPTX | python-pptx + 原始 XML | `gridSpan` / `hMerge` / `rowSpan` / `vMerge` |
| XLSX | openpyxl | `merged_cells.ranges` 保留错柱单元格 |
| CSV | 原生行解析 | |
| HTML | BeautifulSoup / trafilatura | |
| TXT / MD | 直读 | UTF-8 / GBK / Latin-1 回退 |
| 图片（PNG / JPG / ...） | Tesseract OCR | |
| URL | trafilatura | |
| 飞书 wiki / 多维表格 | 飞书 Open API + 自定义解析器 | 已覆盖 10 种 `ui_type` |

表格最终输出为 Markdown 块，后续切片能保留结构。

### 检索 — 混合 + 智能体

- **向量路径**——Chroma 余弦，距离转分数，优先 `mode="query"`，供应商不支持时降级到 `mode="db"`。
- **关键词路径**——SQLite FTS5 BM25，友好处理 CJK，两轮查询（短语 + 单词 OR + LIKE 回退）。
- **合并**——按 `(note_id, chunk_index)` 去重，分数 `0.7 * vec + 0.3 * kw`，顶部 K 位加阈值过滤低质量引用。
- **多轮研究 agent**——最多 3 轮，后续查询由中型 LLM 生成，赊够的切片集起来后提前结束。
- **RAG 评测**——`python scripts/rag_eval/run.py --out report.md` 输出含分类拆解的 Markdown 报告。

### LLM — 多提供商

- OpenAI、Anthropic（原生）
- DeepSeek、智谱 GLM、月之清江 Kimi、SiliconFlow、Ollama（OpenAI 兼容 `base_url`）
- MiniMax（`embo-01` 等），原生 body + 自动 mode 回退
- 每请求可覆盖：`base_url` / `api_key` / `model` / `reasoning_level` / `embedding_model`

### 飞书集成

- OAuth（`app_id + app_secret` -> `tenant_access_token`，缓存 2 小时）
- DFS 遍历 wiki 空间与多维表格
- 增量同步：对比 `obj_edit_time` 与 `Note.source_revision`，变更的页面原 id 重入库（不打断引用）
- 后台循环间隔可由 `FEISHU_SYNC_INTERVAL_MIN` 配置
- 手动触发：`POST /api/feishu/sync { "space_id": "...", "force_full": true }`

### 前端

- Vue 3 + Vite + naive-ui + Pinia
- HD 蓝主题（`#3b82f6`）
- SSE 流式响应 + 阶段指示器（intent / research / ingest / report）
- 引用卡片可点回原文片段
- `IngestResultCard` 渲染结构化入库元信息（标题 / 标签 / 摘要 / 重复提示）

---

## 架构

```mermaid
flowchart TB
    U[用户输入] --> R[路由器<br/>轻量 LLM<br/>意图 + 重写]
    R -->|聊天| RT[检索]
    R -->|研究| RS[研究<br/>多轮]
    R -->|入库| IG[入库<br/>URL / 文本 / 去重]
    R -->|周报| RP[周报<br/>时间窗口]
    RT --> A[生成答案<br/>LLM 流式]
    RS --> A
    IG --> A
    RP --> A
    A --> C[引用切片<br/>跳回原文]
```

> 保留老的直调链路：设 `HD_USE_GRAPH=false` 即可。

---

## 快速开始

### 环境准备

- Python 3.10+
- Node.js 18+
- （可选）Tesseract + `chi_sim.traineddata`，用于 OCR
- （可选）任一个 OpenAI 兼容接口（OpenAI / Anthropic / DeepSeek / 智谱 / 月之清江 / SiliconFlow / Ollama ...）

### 安装

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env       # 填奴 LLM_API_KEY + EMBEDDING_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Frontend（另开一个终端）
cd ..\frontend
npm install
npm run dev                   # http://127.0.0.1:5174
```

打开 `http://127.0.0.1:5174`，进入**设置 -> 添加自定义模型**，填入 OpenAI 兼容的 `Base URL` / `API Key` 与检测到的模型名，再进入**知识库**上传文件。

一键启动脚本：`scripts/start-all.ps1`。

---

## 使用

### 上传 + 问答

1. **知识库** -> 上传 PDF / Word / 图片 / 文本 / URL。
2. 等状态从 `embedding` 变为 `N chunks`。
3. **聊天**页 -> 打开知识库开关，开始问答。

### 开启飞书同步

```env
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_SPACE_IDS=7676363835179207668      # 为空 = 所有可见空间
FEISHU_SYNC_INTERVAL_MIN=15                # 0 = 仅手动
```

后续第二次同步应该报 `synced=0 skipped=N`。

### 跑 RAG 评测

```powershell
cd backend
.\.venv\Scripts\python.exe ..\scripts\rag_eval\run.py --top-k 5 --out report.md
```

输出 Recall@K、MRR、闲聊误引率以及每个样本的分类拆解。

### 跑表格识别测试

```powershell
cd scripts\table_tests
..\backend\.venv\Scripts\python.exe run_all.py
```

没 Tesseract 能跑过 5/6；装 Tesseract 后可以解锁扫描 PDF 场景。

---

## 配置

环境变量（详见 `backend/.env.example`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `deepseek` / `zhipu` / `moonshot` / `siliconflow` / `ollama` / 自定义 |
| `LLM_MODEL` | `gpt-4o-mini` | 聊天模型 |
| `LLM_API_KEY` | （空） | 提供商的 Bearer key |
| `LLM_API_BASE` | （空） | 覆盖默认 base URL |
| `EMBEDDING_*` | 同 `LLM_*` | 向量配置；MiniMax `embo-01` 请设 `EMBEDDING_MODEL=embo-01` |
| `HD_USE_GRAPH` | `true` | LangGraph 驱动 SSE；设 `false` 回退直调 |
| `HD_ROUTER_ENABLED` | `true` | 关闭则总是走 `chat` |
| `HD_ROUTER_MODEL` | （空） | 可选轻量路由模型 |
| `HD_RESEARCH_MAX_ITER` | `3` | 研究 agent 最多轮数 |
| `HD_RESEARCH_TARGET_CHUNKS` | `8` | 赊走够多切片后提前结束 |
| `FEISHU_*` | 见 `.env.example` | 飞书集成 |
| `HD_MAX_UPLOAD_BYTES` | `52428800` | 50 MB 上传上限 |
| `HD_ALLOWED_ORIGINS` | `http://127.0.0.1:5174` | CORS 白名单，多个用逗号分隔 |

---

## 文档

- [docs/FEATURES.md](docs/FEATURES.md) — 完整功能清单
- [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md) — v1.1 升级计划 + 验收记录
- [docs/RAG.md](docs/RAG.md) — RAG 三层管道深入解析
- [docs/PLAN.md](docs/PLAN.md) — 原始路线图（P0-P9）
- [docs/STATUS.md](docs/STATUS.md) — 历史变更记录
- [docs/file-writing-policy.md](docs/file-writing-policy.md) — UTF-8 no-BOM 约定

---

## 路线图

详见 `docs/OPTIMIZATION.md` v1.1 验收表。待完成项：

- 可选鉴权（`HD_ACCESS_TOKEN` Bearer）供公开部署
- HTTPS + Cloudflare Tunnel 重启公网
- NSSM 自动安装（`scripts/install-service.ps1`，需手动开启）
- 可选 PaddleOCR `PP-StructureV2`，提高扫描表格质量

---

## 许可证

MIT 许可证 — 见 `LICENSE`。

---

## 参与贡献

PR 欢迎。提交前请本地跑表格测试和 RAG 评测，确认没有回归：

```powershell
cd scripts\table_tests && ..\backend\.venv\Scripts\python.exe run_all.py
cd ..\..\backend && .\..\backend\.venv\Scripts\python.exe ..\scripts\rag_eval\run.py --out report.md
```
