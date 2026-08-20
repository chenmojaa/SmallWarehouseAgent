import { get, postJson, deleteReq, postJsonPatch } from './client'
import type { Citation } from './chat'

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  preview: string
}

export interface ChatMessageRecord {
  id: number
  role: "user" | "assistant" | "system"
  content: string
  citations?: Citation[]
  created_at: string
}

export interface SessionDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: ChatMessageRecord[]
}

export async function listSessions(): Promise<Session[]> {
  const r = await get<{ items: Session[] }>("/sessions")
  return r.items
}

export async function createSession(title?: string): Promise<Session> {
  return postJson<Session>("/sessions", { title })
}

export async function getSessionDetail(id: string): Promise<SessionDetail> {
  return get<SessionDetail>("/sessions/" + id)
}

export async function deleteSession(id: string): Promise<{ deleted: string }> {
  return deleteReq("/sessions/" + id) as Promise<{ deleted: string }>
}

export async function renameSession(id: string, title: string) {
  return postJsonPatch("/sessions/" + id, { title })
}