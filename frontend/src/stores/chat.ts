import { defineStore } from 'pinia'
import { chatStream, stripThink, type ChatMessage, type Citation } from '@/api/chat'
import { useSettingsStore } from './settings'
import { useModelsStore } from './models'
import { useSessionsStore } from './sessions'

interface Msg extends ChatMessage { id: string; citations?: Citation[]; activeCitationIndex?: number | null }
export interface PipelineStage {
  stage: "rag_search" | "llm_stream"
  status: "started" | "done"
  ms?: number
  hits?: number
  at: number
}

interface State {
  sessionId: string | null
  messages: Msg[]
  isStreaming: boolean
  error: string | null
  useRag: boolean
  abortCtl: AbortController | null
  streamingSessionId: string | null
  stage: PipelineStage | null
  // Saved in-flight messages when the user navigates AWAY from a streaming
  // session. Restored when they come back so the partial answer + the
  // thinking row don't disappear the moment they click another row.
  streamingSnapshot: Msg[] | null
}

export const useChatStore = defineStore("chat", {
  state: (): State => ({
    sessionId: null,
    isStreaming: false,
    messages: [],
    error: null,
    useRag: true,
    abortCtl: null,
    streamingSessionId: null,
    stage: null,
    streamingSnapshot: null,
  }),
  getters: {
    streamingHere: (s): boolean => s.isStreaming && s.streamingSessionId !== null && s.streamingSessionId === s.sessionId,
  },
  actions: {
    toggleRag() { this.useRag = !this.useRag },
        async send(text: string) {
      if (!text.trim()) return
    if (this.streamingSessionId !== null && this.streamingSessionId === this.sessionId) return
      const userMsg: Msg = { id: 'u-' + String(Date.now()), role: 'user', content: text }
      const asstMsg: Msg = { id: 'a-' + String(Date.now() + 1), role: 'assistant', content: '' }
      this.messages.push(userMsg, asstMsg)
      this.isStreaming = true
      this.streamingSessionId = this.sessionId
      this.error = null
      this.stage = null
      this.abortCtl = new AbortController()

      const models = useModelsStore()
      const sessions = useSessionsStore()
      const history: ChatMessage[] = this.messages
        .filter(m => m.id !== asstMsg.id)
        .map(m => ({ role: m.role, content: m.content }))

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
          } else if (ev.type === 'error') {
            const msg = (ev.data && typeof ev.data === 'string') ? ev.data : String(ev.data ?? 'unknown error')
            visible += '\n\n[Error] ' + msg
            flushBubble()
            this.error = msg
          } else if (ev.type === 'done') {
            if (inThink) {
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
        this.abortCtl = null
        this.stage = null
        this.streamingSnapshot = null
      }
    },
    async loadFromSession(sessionId: string) {
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
        this.streamingSessionId !== null && this.messages.length > 0

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
        this.streamingSnapshot = [...this.messages]
      }

      const sessions = useSessionsStore()
      await sessions.loadDetail(sessionId)
      const detail = sessions.currentDetail
      if (!detail) { this.error = "Session not found"; return }

      // Coming back to a still-streaming session from somewhere else.
      if (this.streamingSnapshot && this.streamingSessionId === sessionId) {
        this.sessionId = detail.id
        this.messages = this.streamingSnapshot
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
      this.streamingSnapshot = null
      this.error = null
    },
    clear() {
      // Same as loadFromSession: keep the background stream alive.
      this.sessionId = null
      this.messages = []
      this.streamingSnapshot = null
      this.error = null
    },
    setActiveCitation(msgId: string, idx: number | null) {
      const i = this.messages.findIndex(m => m.id === msgId)
      if (i >= 0) this.messages[i] = { ...this.messages[i], activeCitationIndex: idx }
    },
  },
})