import { defineStore } from 'pinia'
import { listSessions, createSession, deleteSession, getSessionDetail, forkSession, type Session, type SessionDetail } from '@/api/sessions'

interface State {
  items: Session[]
  loading: boolean
  error: string | null
  currentDetail: SessionDetail | null
}

const SESSIONS_CACHE_KEY = 'hd_sessions_cache_v1'

function readSessionsCache(): Session[] {
  try {
    const raw = localStorage.getItem(SESSIONS_CACHE_KEY)
    const value = raw ? JSON.parse(raw) : null
    return Array.isArray(value) ? value as Session[] : []
  } catch {
    return []
  }
}

export const useSessionsStore = defineStore("sessions", {
  state: (): State => ({ items: [], loading: false, error: null, currentDetail: null }),
  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        this.items = await listSessions()
        localStorage.setItem(SESSIONS_CACHE_KEY, JSON.stringify(this.items))
      }
      catch (e) {
        this.error = (e as Error)?.message || String(e)
        const cached = readSessionsCache()
        if (cached.length > 0) this.items = cached
      }
      finally { this.loading = false }
    },
    async createNew(title?: string) {
      const s = await createSession(title)
      this.items.unshift({
        ...s,
        message_count: 0,
        preview: "",
        updated_at: s.created_at,
      })
      return s
    },
    async remove(id: string) {
      try {
        await deleteSession(id)
        this.items = this.items.filter(s => s.id !== id)
        if (this.currentDetail?.id === id) this.currentDetail = null
      } catch (e) {
        this.error = (e as Error).message
      }
    },
    async fork(id: string, title?: string) {
      // Clone the session + all messages into a new session, then prepend it to
      // the list and set it as the active detail. Used by the "fork" button on
      // each session row in ChatHistory.vue.
      const forked = await forkSession(id, title)
      this.items.unshift({
        id: forked.id,
        title: forked.title,
        created_at: forked.created_at,
        updated_at: forked.updated_at,
        message_count: forked.message_count ?? 0,
        preview: forked.preview ?? "",
      })
      try { await this.loadDetail(forked.id) } catch { /* ignore */ }
      return forked
    },
    async loadDetail(id: string) {
      this.loading = true
      this.currentDetail = null
      try {
        this.currentDetail = await getSessionDetail(id)
      } catch (e) {
        this.error = (e as Error).message
      } finally {
        this.loading = false
      }
    },
    clearDetail() { this.currentDetail = null },
  },
})
