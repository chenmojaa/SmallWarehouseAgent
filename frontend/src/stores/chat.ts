import { defineStore } from 'pinia'
import { chatStream, stripThink, type ChatMessage, type Citation, type IngestResult, type ReportResult } from '@/api/chat'
import { useSettingsStore } from './settings'
import { useModelsStore } from './models'
import { useSessionsStore } from './sessions'

interface Msg extends ChatMessage {
  id: string
  citations?: Citation[]
  activeCitationIndex?: number | null
  ingest?: IngestResult
  report?: ReportResult
}
export interface PipelineStage {
  stage: "router" | "rag_search" | "llm_stream" | "agent"
  status: "started" | "done"
  ms?: number
  hits?: number
  intent?: string
  agent?: string
  iterations?: number
  at: number
}

interface State {
  sessionId: string | null
  loadToken: number
  messages: Msg[]
  isStreaming: boolean
  error: string | null
  useRag: boolean
  abortCtl: AbortController | null
  streamingSessionId: string | null
  streamingMessageId: string | null
  stage: PipelineStage | null
  // Saved in-flight messages when the user navigates AWAY from a streaming
  // session. Restored when they come back so the partial answer + the
  // thinking row don't disappear the moment they click another row.
  streamingSnapshot: Msg[] | null
  // True while the LLM is inside a <think>...</think> block during streaming.
  // ChatView uses this to swap the placeholder label to "思考中..." so the
  // user gets a hint that the model is reasoning (not stalling) before the
  // first body token arrives.
  thinking: boolean
}

export const useChatStore = defineStore("chat", {
  state: (): State => ({
    sessionId: null,
    loadToken: 0,
    isStreaming: false,
    messages: [],
    error: null,
    useRag: true,
    abortCtl: null,
    streamingSessionId: null,
    streamingMessageId: null,
    stage: null,
    streamingSnapshot: null,
    thinking: false,
  }),
  getters: {
    streamingHere: (s): boolean => s.isStreaming && s.streamingSessionId !== null && s.streamingSessionId === s.sessionId,
  },
  actions: {
    toggleRag() { this.useRag = !this.useRag },
    async send(text: string) {
      if (!text.trim()) return
      if (this.isStreaming) return
    if (this.streamingSessionId !== null && this.streamingSessionId === this.sessionId) return
      const userMsg: Msg = { id: 'u-' + String(Date.now()), role: 'user', content: text }
      const asstMsg: Msg = { id: 'a-' + String(Date.now() + 1), role: 'assistant', content: '' }
      this.messages.push(userMsg, asstMsg)
      this.isStreaming = true
      this.streamingSessionId = this.sessionId
      this.streamingMessageId = asstMsg.id
      this.error = null
      this.stage = null
      this.abortCtl = new AbortController()

      const models = useModelsStore()
      const sessions = useSessionsStore()
      // Phase 3.5: stop shipping the entire conversation history in every
      // request. The backend now reads history from the DB (Phase 2) so the
      // only payload it actually needs is the current turn. This shrinks the
      // request body to O(1) regardless of session length and removes a
      // class of frontend tampering concerns. Legacy field kept as `messages`
      // for backend type compatibility, but only the one entry is sent.
      const history: ChatMessage[] = [{ role: 'user', content: text }]

      const sel = models.selected
      const provider = sel?.provider
      const model = sel?.modelName
      const baseUrl = sel?.baseUrl
      const apiKey = sel?.apiKey
      const reasoning = sel?.reasoning
      const embeddingModel = sel?.embeddingModel

      // Stream-time <think> state machine: avoids re-scanning the full
      // accumulated text on every token. The previous version ran 3 regex
      // passes over the whole buffer per delta, which scaled badly with
      // long answers.
      let visible = ''
      let inThink = false

      const feed = (raw: string): void => {
        let s = raw
        while (s.length) {
          if (!inThink) {
            const open = s.indexOf('<think>')
            if (open === -1) {
              visible += s
              s = ''
            } else {
              visible += s.slice(0, open)
              s = s.slice(open + 7)
              if (!inThink) this.thinking = true
              inThink = true
            }
          } else {
            const close = s.indexOf('</think>')
            if (close === -1) {
              // Still inside <think>; flush whatever we have on next delta
              // or on `done` (which will trim any tail that never closed).
              return
            }
            s = s.slice(close + 8)
            if (inThink) this.thinking = false
            inThink = false
          }
        }
      }

      const flushBubble = (): void => {
        asstMsg.content = visible.trimEnd()
        const idx = this.messages.findIndex(m => m.id === asstMsg.id)
        if (idx >= 0) this.messages[idx] = { ...asstMsg }
      }

      try {
        const stream = chatStream({
          messages: history,
          provider: provider ?? null,
          model: model ?? null,
          use_rag: this.useRag,
          session_id: this.sessionId,
          base_url: baseUrl ?? null,
          api_key: apiKey ?? null,
          reasoning_level: reasoning ?? null,
          embedding_model: embeddingModel ?? null,
          embedding_base_url: baseUrl ?? null,
        }, this.abortCtl?.signal)
        for await (const ev of stream) {
          if (ev.type === 'session' && ev.session_id) {
            this.sessionId = ev.session_id
            if (this.streamingSessionId === null) this.streamingSessionId = ev.session_id
            sessions.load()
          } else if (ev.type === 'delta' && typeof ev.data === 'string') {
            feed(ev.data)
            flushBubble()
          } else if (ev.type === 'stage' && ev.data && typeof ev.data === 'object') {
            this.stage = { ...(ev.data as PipelineStage), at: Date.now() }
          } else if (ev.type === 'citations' && Array.isArray(ev.data)) {
            asstMsg.citations = ev.data as Citation[]
            const idx = this.messages.findIndex(m => m.id === asstMsg.id)
            if (idx >= 0) this.messages[idx] = { ...asstMsg }
          } else if (ev.type === 'ingest' && ev.data) {
            asstMsg.ingest = ev.data as IngestResult
            const idx = this.messages.findIndex(m => m.id === asstMsg.id)
            if (idx >= 0) this.messages[idx] = { ...asstMsg }
          } else if (ev.type === 'report' && ev.data) {
            asstMsg.report = ev.data as ReportResult
            const idx = this.messages.findIndex(m => m.id === asstMsg.id)
            if (idx >= 0) this.messages[idx] = { ...asstMsg }
          } else if (ev.type === 'error') {
            const msg = (ev.data && typeof ev.data === 'string') ? ev.data : String(ev.data ?? 'unknown error')
            visible += '\n\n[Error] ' + msg
            flushBubble()
            this.error = msg
          } else if (ev.type === 'done') {
            if (inThink) {
              // LLM ended without ever emitting a </think>; close it out so
              // the placeholder doesn't keep flashing "思考中..." forever.
              this.thinking = false
              visible = visible.replace(/<think>[\s\S]*$/, '')
              flushBubble()
            }
            break
          }
        }
        sessions.load()
      } catch (e) {
        // Ignore aborts (user switched sessions or hit +new chat).
        if (this.abortCtl?.signal.aborted) return
        const errMsg = (e as Error).message || String(e)
        this.error = errMsg
        visible += '\n\n[Error] ' + errMsg
        flushBubble()
      } finally {
        this.isStreaming = false
        this.streamingSessionId = null
        this.streamingMessageId = null
        this.abortCtl = null
        this.stage = null
        this.thinking = false
        this.streamingSnapshot = null
      }
    },
    async loadFromSession(sessionId: string) {
      const token = ++this.loadToken
      this.error = null
      // Three in-flight scenarios we have to protect so the partial answer and
      // the thinking row don't disappear the moment the user navigates:
      //
      //   (A) Already on this session with in-flight messages -> keep them.
      //   (B) In welcome state (this.sessionId === null) and the freshly-created
      //       streaming session is now being opened from the sidebar -> keep
      //       in-flight, don't overwrite with stale DB rows.
      //   (C) Navigating AWAY from the streaming session -> save snapshot so
      //       we can restore when they come back.
      const inFlight =
        // Decoupled from messages.length on purpose: when the user navigates
        // away mid-stream, ChatView routes through `clear()` which (after
        // the fix below) keeps messages intact but zeros sessionId. Relying
        // on messages.length here would incorrectly classify that as "not
        // in flight" and we'd overwrite the live state with stale DB rows.
        this.isStreaming && this.streamingSessionId !== null

      const sameSessionReopen =
        inFlight &&
        this.streamingSessionId === sessionId &&
        (this.sessionId === sessionId || this.sessionId === null)

      const leavingStream =
        inFlight &&
        this.sessionId === this.streamingSessionId &&
        this.streamingSessionId !== sessionId

      if (sameSessionReopen) {
        // (A)/(B): no DB fetch needed, the live state is already the most
        // up-to-date view (DB only has the user message at this point).
        this.sessionId = sessionId
        this.error = null
        return
      }

      if (leavingStream) {
        // (C): save in-flight state for the round-trip.
        const messages = [...this.messages]
        const assistantId = this.streamingMessageId
        if (assistantId && !messages.some(m => m.id === assistantId)) {
          messages.push({ id: assistantId, role: 'assistant', content: '' })
        }
        this.streamingSnapshot = messages
      }

      const sessions = useSessionsStore()
      await sessions.loadDetail(sessionId)
      if (token !== this.loadToken) return
      const detail = sessions.currentDetail
      if (!detail || detail.id !== sessionId) { this.error = "Session not found"; return }

      // Coming back to a still-streaming session from somewhere else.
      if (this.isStreaming && this.streamingSnapshot && this.streamingSessionId === sessionId) {
        this.sessionId = detail.id
        const messages = [...this.streamingSnapshot]
        const assistantId = this.streamingMessageId
        if (assistantId && !messages.some(m => m.id === assistantId)) {
          messages.push({ id: assistantId, role: 'assistant', content: '' })
        }
        this.messages = messages
        this.streamingSnapshot = null
        this.error = null
        return
      }

      this.sessionId = detail.id
      // Keep the leading <think>...</think> block intact here; MessageBubble
      // renders it as a collapsible details section so the user can still
      // see the model's reasoning when re-opening a past conversation.
      this.messages = detail.messages.map(m => ({
        id: "h-" + String(m.id),
        role: m.role as "user" | "assistant" | "system",
        content: m.content,
        citations: m.citations || undefined,
      }))
      const snapshotBelongsToBackgroundStream =
        this.isStreaming &&
        this.streamingSnapshot !== null &&
        this.streamingSessionId !== null &&
        this.streamingSessionId !== sessionId
      if (!snapshotBelongsToBackgroundStream) {
        this.streamingSnapshot = null
      }
      this.error = null
    },
    clear() {
      // If a background stream is still running, leaving (e.g. clicking
      // "知识库" / Skill / 搜索对话) must NOT wipe messages or snapshot.
      // `loadFromSession` is the only place that knows how to restore the
      // snapshot; if we zero it here, the user's next click back into the
      // session lands on stale DB rows and the in-flight assistant bubble
      // (including the streaming "思考中..." placeholder) disappears.
      if (this.isStreaming && this.streamingSessionId !== null && this.messages.length > 0) {
        const messages = [...this.messages]
        const assistantId = this.streamingMessageId
        if (assistantId && !messages.some(m => m.id === assistantId)) {
          messages.push({ id: assistantId, role: 'assistant', content: '' })
        }
        this.streamingSnapshot = messages
        this.sessionId = null
        this.error = null
        return
      }
      this.sessionId = null
      this.messages = []
      this.streamingSnapshot = null
      this.error = null
    },
    setActiveCitation(msgId: string, idx: number | null) {
      const i = this.messages.findIndex(m => m.id === msgId)
      if (i >= 0) this.messages[i] = { ...this.messages[i], activeCitationIndex: idx }
    },
    /** 删除一条消息（及其配对消息） */
    deleteMessage(msgId: string) {
      const i = this.messages.findIndex(m => m.id === msgId)
      if (i < 0) return
      const msg = this.messages[i]
      // 删用户消息时连带后面的 assistant；删 assistant 时连带前面的 user
      if (msg.role === 'user' && i + 1 < this.messages.length && this.messages[i + 1].role === 'assistant') {
        this.messages.splice(i, 2)
      } else if (msg.role === 'assistant' && i > 0 && this.messages[i - 1].role === 'user') {
        this.messages.splice(i - 1, 2)
      } else {
        this.messages.splice(i, 1)
      }
    },
    /** 重新生成：删除最后一条 assistant，用其前一条 user 重新发送 */
    async regenerate() {
      if (this.isStreaming) return
      const last = this.messages[this.messages.length - 1]
      if (!last || last.role !== 'assistant') return
      const prev = this.messages[this.messages.length - 2]
      if (!prev || prev.role !== 'user') return
      this.messages.pop() // 删掉这条 assistant
      const text = prev.content
      await this.send(text)
    },
    /** 回退：删除最后一条 user + assistant */
    undoLast() {
      if (this.isStreaming) return
      const n = this.messages.length
      if (n >= 2 && this.messages[n - 1].role === 'assistant' && this.messages[n - 2].role === 'user') {
        this.messages.splice(n - 2, 2)
      } else if (n >= 1) {
        this.messages.pop()
      }
    },
  },
})
