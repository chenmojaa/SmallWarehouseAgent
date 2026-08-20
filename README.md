# HD 鈥?Personal Knowledge Base Agent

HD is a local-first personal knowledge base that pairs a multi-format inbox with hybrid (vector + keyword) retrieval, multi-LLM chat, and a Vue 3 frontend.

## Stack
- Backend: FastAPI + LangChain + LangGraph + Chroma + SQLite (FTS5)
- Frontend: Vue 3 + Vite + naive-ui + Pinia
- Embeddings: OpenAI-compatible `/v1/embeddings` (OpenAI, MiniMax, ...)
- LLMs: OpenAI-compatible `/v1/chat/completions`

## Quick start (Windows / PowerShell)

```powershell
# 1. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env       # then fill LLM_API_KEY / EMBEDDING_API_KEY

# start (port 8001)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 2. Frontend (new shell)
cd frontend
npm install
npm run dev                  # http://127.0.0.1:5174
```

Open `http://127.0.0.1:5174`. In **Settings -> Add custom model**, paste your OpenAI-compatible `Base URL` + `API Key` + detected model names, then visit **Knowledge Base** to upload PDFs, images (OCR), Office files, or text.

## Knowledge Base features
- Multi-format ingest: PDF, DOCX, PPTX, XLSX, CSV, HTML, TXT/MD, images (OCR via Tesseract)
- Sliding-window text chunking (500 chars / 80 overlap)
- Hybrid retrieval: Chroma cosine vector + SQLite FTS5 BM25
  - combined score = 0.7 * vec_score + 0.3 * kw_score, top_k = 5
- Per-note re-embedding with `X-API-Key` / `X-Embedding-Base-URL` / `X-Embedding-Model` headers

## License
MIT