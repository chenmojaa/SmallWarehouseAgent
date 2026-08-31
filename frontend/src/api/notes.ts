import { get, postJson, deleteReq, authTokenHeaders } from './client'
import { useModelsStore } from '@/stores/models'

export interface Note {
  id: string
  title: string
  source_type: string
  source_url?: string
  content_path?: string
  summary?: string
  tags?: string
  word_count: number
  chunk_count: number
  embedded: boolean
  created_at?: string
  view_url?: string | null
}

export interface NotesList {
  items: Note[]
  total: number
  limit: number
  offset: number
}

export interface NotesStats {
  sqlite: { total_notes: number; embedded_notes: number }
  chroma: { count: number; name: string }
}

export async function listNotes(limit = 50, offset = 0): Promise<NotesList> {
  return get<NotesList>(`/notes?limit=${limit}&offset=${offset}`)
}

export async function getNote(id: string): Promise<Note> {
  return get<Note>(`/notes/${id}`)
}

function authHeaders(): Record<string, string> {
  const out: Record<string, string> = {}
  // 1) Prefer the currently-selected custom LLM's key + baseUrl.
  try {
    const sel = useModelsStore().selected
    if (sel?.apiKey) out["X-API-Key"] = sel.apiKey
    if (sel?.baseUrl) out["X-Embedding-Base-URL"] = sel.baseUrl
    if (sel?.embeddingModel) out["X-Embedding-Model"] = sel.embeddingModel
    // Fallback embedding model when user did not fill the dedicated field.
    // MiniMax chat models pair with embo-01 by default.
    if (!out["X-Embedding-Model"] && sel?.baseUrl && /minimax/i.test(sel.baseUrl)) {
      out["X-Embedding-Model"] = "embo-01"
    }
  } catch {}
  // Fallback to the global key in localStorage
  if (!out["X-API-Key"]) {
    try {
      const k = localStorage.getItem("second_brain_api_key") || ""
      if (k) out["X-API-Key"] = k
    } catch {}
  }
  // 登录 token（受保护 API 必需）
  Object.assign(out, authTokenHeaders())
  return out
}

export async function reembedNote(id: string): Promise<Note> {
  const resp = await fetch("/api/notes/" + id + "/reembed", {
    method: "POST",
    headers: authHeaders(),
  })
  if (!resp.ok) throw new Error(resp.status + " " + (await resp.text()))
  return resp.json() as Promise<Note>
}

export async function ingestUrl(url: string): Promise<Note> {
  return postJson<Note>("/notes/url", { url })
}

export async function ingestText(text: string, title?: string): Promise<Note> {
  return postJson<Note>("/notes/text", { text, title })
}

export async function ingestFile(file: File, lang = "chi_sim+eng", signal?: AbortSignal): Promise<Note> {
  const fd = new FormData()
  fd.append("file", file)
  const url = `/notes/file${lang ? "" : ""}` // always use /notes/file
  const resp = await fetch("/api" + url, {
    method: "POST",
    headers: authHeaders(),
    body: fd,
    signal,
  })
  if (!resp.ok) throw new Error(resp.status + " " + (await resp.text()))
  return resp.json() as Promise<Note>
}

export async function ingestImage(file: File, lang = "chi_sim+eng", signal?: AbortSignal): Promise<Note> {
  const fd = new FormData()
  fd.append("file", file)
  fd.append("lang", lang)
  const resp = await fetch("/api/notes/image", {
    method: "POST",
    headers: authHeaders(),
    body: fd,
    signal,
  })
  if (!resp.ok) throw new Error(resp.status + " " + (await resp.text()))
  return resp.json() as Promise<Note>
}

export async function deleteNote(id: string) {
  return deleteReq(`/notes/${id}`)
}

export async function getStats(): Promise<NotesStats> {
  return get<NotesStats>("/notes-stats")
}
