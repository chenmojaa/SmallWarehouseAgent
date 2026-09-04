import { postJson, streamSse } from './client'

export interface ChatMessage {
  role: "user" | "assistant" | "system"
  content: string
}

export interface Citation {
  note_id: string
  title?: string
  chunk_index: number
  snippet: string
  score?: number
  source_type?: string
  source_url?: string
}

export interface ChatRequest {
  messages: ChatMessage[]
  provider?: string | null
  model?: string | null
  use_rag?: boolean
  use_planner?: boolean | null
  session_id?: string | null
  base_url?: string | null
  api_key?: string | null
  reasoning_level?: string | null
  embedding_model?: string | null
  embedding_base_url?: string | null
  agent_permission?: 'default' | 'full'
}

/** 歧义澄清请求（router 判定问题有歧义时经 SSE 下发） */
export interface ClarifyEvent {
  request_id: string
  question: string
  options: string[]
}

export interface StageEvent {
  stage: "router" | "rag_search" | "llm_stream" | "agent"
  status: "started" | "done"
  ms?: number
  hits?: number
  intent?: string
  rewritten_query?: string
  agent?: string
  iterations?: number
  steps?: number
  plan_summary?: string
  step?: number | null
  total_steps?: number
  query?: string
}

export interface PlanStepItem {
  query: string
  status: "pending" | "running" | "done"
  hits?: number
  replan?: boolean
}

export interface PlanEvent {
  phase: "created" | "step_done" | "replan" | "done"
  summary?: string
  queries?: string[]
  index?: number
  query?: string
  hits?: number
  iterations?: number
}

export interface IngestResult {
  ok: boolean
  note_id?: string
  title?: string
  tags?: string[]
  summary?: string
  source_type?: string
  embedded?: boolean
  chunk_count?: number
  duplicate_of?: number | null
  error?: string
}

export interface ReportResult {
  ok: boolean
  empty?: boolean
  period_days?: number
  note_id?: string
  counts?: { notes: number; tags: number }
  summary?: string
  message?: string
}

export interface ToolEvent {
  phase: "start" | "call" | "result"
  name?: string
  calls?: string[]
  args?: unknown
  ok?: boolean
  snippet?: string
}

export interface PermissionEvent {
  phase: "request" | "result"
  request_id: string
  tool?: string
  args?: unknown
  approved?: boolean
}

export interface ChatStreamEvent {
  type: "session" | "delta" | "citations" | "done" | "error" | "stage" | "ingest" | "report" | "tool" | "permission" | "plan" | "clarify"
  session_id?: string
  data?: string | Citation[] | StageEvent | IngestResult | ReportResult | ToolEvent | PermissionEvent | PlanEvent | ClarifyEvent
}

/** 回复 Agent 的本地访问权限请求（允许 / 拒绝） */
export async function respondPermission(requestId: string, approve: boolean): Promise<{ ok: boolean }> {
  return postJson<{ ok: boolean }>('/chat/permission', { request_id: requestId, approve })
}

/** 回复歧义澄清（点选项 / 自由输入；空串=跳过，按原问题继续） */
export async function respondClarify(requestId: string, answer: string): Promise<{ ok: boolean }> {
  return postJson<{ ok: boolean }>('/chat/clarify', { request_id: requestId, answer })
}

// 移除 <think>...</think> 思考段落（配对的 + 未闭合的尾部）
export function stripThink(s: string): string {
  if (!s) return s
  return s
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<think>[\s\S]*$/gi, '')
    .replace(/<\/think>/gi, '')
    .trim()
}

export async function* chatStream(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<ChatStreamEvent> {
  const stream = streamSse("/chat", {
    messages: req.messages,
    provider: req.provider || undefined,
    model: req.model || undefined,
    use_rag: req.use_rag !== false,
    use_planner: req.use_planner === undefined ? undefined : req.use_planner,
    session_id: req.session_id || undefined,
    base_url: req.base_url || undefined,
    api_key: req.api_key || undefined,
    reasoning_level: req.reasoning_level || undefined,
    embedding_model: req.embedding_model || undefined,
    embedding_base_url: req.embedding_base_url || undefined,
    agent_permission: req.agent_permission || "default",
  }, signal)
  for await (const ev of stream) {
    if (ev.data === "[DONE]") { yield { type: "done" }; return }
    if (ev.event === "session") {
      try {
        const obj = JSON.parse(ev.data)
        yield { type: "session", session_id: obj.session_id }
      } catch {}
    } else if (ev.event === "citations") {
      try { yield { type: "citations", data: JSON.parse(ev.data) } }
      catch {}
    } else if (ev.event === "stage") {
      try { yield { type: "stage", data: JSON.parse(ev.data) } }
      catch {}
    } else if (ev.event === "tool") {
      try { yield { type: "tool", data: JSON.parse(ev.data) } } catch {}
    } else if (ev.event === "permission") {
      try { yield { type: "permission", data: JSON.parse(ev.data) } } catch {}
    } else if (ev.event === "plan") {
      try { yield { type: "plan", data: JSON.parse(ev.data) } } catch {}
    } else if (ev.event === "clarify") {
      try { yield { type: "clarify", data: JSON.parse(ev.data) } } catch {}
    } else if (ev.event === "error") {
      yield { type: "error", data: ev.data }
    } else if (ev.event === "ingest") {
      try { yield { type: "ingest", data: JSON.parse(ev.data) } } catch {}
    } else if (ev.event === "report") {
      try { yield { type: "report", data: JSON.parse(ev.data) } } catch {}
    } else {
      yield { type: "delta", data: ev.data }
    }
  }
}
