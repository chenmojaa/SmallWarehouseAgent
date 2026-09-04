import { defineStore } from 'pinia'
import { chatStream, planPreview, respondPermission, stripThink, type ChatMessage, type ChatRequest, type Citation, type IngestResult, type ReportResult, type ToolEvent, type PermissionEvent, type PlanStepItem, type PlanEvent } from '@/api/chat'
import { useSettingsStore } from './settings'
import { useModelsStore } from './models'
import { useSessionsStore } from './sessions'

export interface ToolCallItem {
  name: string
  status: 'running' | 'ok' | 'failed'
  snippet?: string
}

export interface PendingPermission {
  requestId: string
  tool: string
  args: unknown
}

/** HITL 计划审批卡片状态：pending=待用户批准；approved=已批准执行中；cancelled=已取消 */
export interface PlanApprovalState {
  status: 'pending' | 'approved' | 'cancelled'
  summary: string
  steps: string[]
}

interface Msg extends ChatMessage {
  id: string
  citations?: Citation[]
  activeCitationIndex?: number | null
  ingest?: IngestResult
  report?: ReportResult
  toolCalls?: ToolCallItem[]
  // 任务规划：计划摘要 + 步骤执行状态（plan-strip 渲染）
  planSummary?: string
  planSteps?: PlanStepItem[]
  // HITL 计划审批：待批准的计划卡片（仅内存，不入库）
  planApproval?: PlanApprovalState
}
export interface PipelineStage {
  stage: "router" | "rag_search" | "llm_stream" | "agent"
  status: "started" | "done"
  ms?: number
  hits?: number
  intent?: string
  agent?: string
  iterations?: number
  steps?: number
  plan_summary?: string
  step?: number | null
  total_steps?: number
  query?: string
  at: number
}

interface State {
  sessionId: string | null
  loadToken: number
  messages: Msg[]
  isStreaming: boolean
  error: string | null
  useRag: boolean
  // 任务规划开关：research 意图先分解子查询再检索（localStorage 持久化）
  usePlanner: boolean
  // HITL 计划审批开关：研究意图先出计划卡片，用户批准/编辑后才执行（localStorage 持久化）
  planApproval: boolean
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
  // Agent 本地访问权限：default=每次访问前询问；full=完全访问不询问
  agentPermission: 'default' | 'full'
  // 当前待用户批准的权限请求（弹窗数据）
  pendingPermission: PendingPermission | null
}

export const useChatStore = defineStore("chat", {
  state: (): State => ({
    sessionId: null,
    loadToken: 0,
    isStreaming: false,
    messages: [],
    error: null,
    useRag: true,
    usePlanner: ((): boolean => {
      try { return localStorage.getItem('planner-disabled') !== '1' } catch { return true }
    })(),
    planApproval: ((): boolean => {
      try { return localStorage.getItem('plan-approval') === '1' } catch { return false }
    })(),
    abortCtl: null,
    streamingSessionId: null,
    streamingMessageId: null,
    stage: null,
    streamingSnapshot: null,
    thinking: false,
    agentPermission: ((): 'default' | 'full' => {
      try { return localStorage.getItem('agent-permission') === 'full' ? 'full' : 'default' } catch { return 'default' }
    })(),
    pendingPermission: null,
  }),
  getters: {
    streamingHere: (s): boolean => s.isStreaming && s.streamingSessionId !== null && s.streamingSessionId === s.sessionId,
  },
  actions: {
    toggleRag() { this.useRag = !this.useRag },
    togglePlanner() {
      this.usePlanner = !this.usePlanner
      try {
        if (this.usePlanner) localStorage.removeItem('planner-disabled')
        else localStorage.setItem('planner-disabled', '1')
      } catch { /* localStorage 不可用时仅内存生效 */ }
    },
    togglePlanApproval() {
      this.planApproval = !this.planApproval
      try {
        if (this.planApproval) localStorage.setItem('plan-approval', '1')
        else localStorage.removeItem('plan-approval')
      } catch { /* localStorage 不可用时仅内存生效 */ }
    },
    setAgentPermission(mode: 'default' | 'full') {
      this.agentPermission = mode
      try {
        if (mode === 'full') localStorage.setItem('agent-permission', 'full')
        else localStorage.removeItem('agent-permission')
      } catch {}
    },
    // 用户在弹窗中回复权限请求
    async resolvePermission(approve: boolean) {
      const p = this.pendingPermission
      if (!p) return
      this.pendingPermission = null
      try { await respondPermission(p.requestId, approve) } catch {}
    },
    /** 构造 /chat 请求 payload；extra 用于审批批准时附加 plan_override */
    _buildPayload(text: string, extra?: Partial<ChatRequest>): ChatRequest {
      const models = useModelsStore()
      const sel = models.selected
      // Phase 3.5: stop shipping the entire conversation history in every
      // request. The backend reads history from the DB so the only payload it
      // needs is the current turn (O(1) regardless of session length).
      return {
        messages: [{ role: 'user', content: text }],
        provider: sel?.provider ?? null,
        model: sel?.modelName ?? null,
        use_rag: this.useRag,
        use_planner: this.usePlanner,
        session_id: this.sessionId,
        base_url: sel?.baseUrl ?? null,
        api_key: sel?.apiKey ?? null,
        reasoning_level: sel?.reasoning ?? null,
        embedding_model: sel?.embeddingModel ?? null,
        embedding_base_url: sel?.baseUrl ?? null,
        agent_permission: this.agentPermission,
        ...extra,
      }
    },
    /** 清空流式状态（HITL preview 挂起时恢复输入框交互） */
    _endStreaming() {
      this.isStreaming = false
      this.streamingSessionId = null
      this.streamingMessageId = null
      this.abortCtl = null
      this.stage = null
      this.thinking = false
    },
    /** 消费 /chat SSE 流并更新 asstMsg（send 与 approvePlan 共用） */
    async _runStream(asstMsg: Msg, payload: ChatRequest) {
      const sessions = useSessionsStore()

      // Stream-time <think> state machine: preserves think content (not just
      // visible text) so MessageBubble can render the collapsible thinking
      // section during streaming — previously the think text was discarded
      // and only appeared after navigating away and back (when the full
      // content was reloaded from the backend).
      let visible = ''
      let thinkBuf = ''
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
              // Still inside <think>; accumulate and wait for next delta.
              thinkBuf += s
              s = ''
              return
            }
            thinkBuf += s.slice(0, close)
            s = s.slice(close + 8)
            if (inThink) this.thinking = false
            inThink = false
          }
        }
      }

      const flushBubble = (): void => {
        // Prepend the accumulated thinking block so MessageBubble's
        // splitThink() can extract it and render the collapsible section.
        const thinkBlock = thinkBuf ? '<think>\n' + thinkBuf + '\n</think>\n' : ''
        asstMsg.content = (thinkBlock + visible).trimEnd()
        const idx = this.messages.findIndex(m => m.id === asstMsg.id)
        if (idx >= 0) this.messages[idx] = { ...asstMsg }
      }

      try {
        const stream = chatStream(payload, this.abortCtl?.signal)
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
          } else if (ev.type === 'tool' && ev.data && typeof ev.data === 'object') {
            // 工具调用进度：running -> ok/failed，最终渲染为消息上方的工具条
            const t = ev.data as ToolEvent
            if (!asstMsg.toolCalls) asstMsg.toolCalls = []
            if (t.phase === 'call' && t.name) {
              asstMsg.toolCalls.push({ name: t.name, status: 'running' })
            } else if (t.phase === 'result' && t.name) {
              const pending = [...asstMsg.toolCalls].reverse().find(x => x.name === t.name && x.status === 'running')
              if (pending) {
                pending.status = t.ok ? 'ok' : 'failed'
                pending.snippet = t.snippet
              } else {
                asstMsg.toolCalls.push({ name: t.name, status: t.ok ? 'ok' : 'failed', snippet: t.snippet })
              }
            }
            const idx = this.messages.findIndex(m => m.id === asstMsg.id)
            if (idx >= 0) this.messages[idx] = { ...asstMsg }
          } else if (ev.type === 'plan' && ev.data && typeof ev.data === 'object') {
            // 任务规划进度：created -> step_done* -> replan* -> done
            const p = ev.data as PlanEvent
            if (p.phase === 'created' && p.queries?.length) {
              asstMsg.planSummary = p.summary || ''
              asstMsg.planSteps = p.queries.map(q => ({ query: q, status: 'pending' as const }))
              // 计划生成后第一步立即视为执行中
              if (asstMsg.planSteps.length) asstMsg.planSteps[0].status = 'running'
              // HITL：审批卡片 -> 进度条过渡（approvePlan 已清，这里兜底防重复渲染）
              if (asstMsg.planApproval) asstMsg.planApproval = undefined
            } else if (p.phase === 'step_done' && asstMsg.planSteps && typeof p.index === 'number') {
              const st = asstMsg.planSteps[p.index]
              if (st) { st.status = 'done'; st.hits = p.hits ?? 0 }
              const next = asstMsg.planSteps[p.index + 1]
              if (next && next.status === 'pending') next.status = 'running'
            } else if (p.phase === 'replan' && p.query) {
              // 动态补缺：追加一个「补检索」chip
              if (!asstMsg.planSteps) asstMsg.planSteps = []
              asstMsg.planSteps.push({ query: p.query, status: 'done', hits: p.hits ?? 0, replan: true })
            } else if (p.phase === 'done') {
              // 收尾：所有未完成步骤标记完成（计划提前达标终止的情形）
              if (asstMsg.planSteps) {
                for (const st of asstMsg.planSteps) {
                  if (st.status !== 'done') st.status = 'done'
                }
              }
            }
            const idx = this.messages.findIndex(m => m.id === asstMsg.id)
            if (idx >= 0) this.messages[idx] = { ...asstMsg }
          } else if (ev.type === 'permission' && ev.data && typeof ev.data === 'object') {
            // 权限请求（默认模式）：弹窗让用户批准/拒绝本地访问
            const p = ev.data as PermissionEvent
            if (p.phase === 'request') {
              this.pendingPermission = {
                requestId: p.request_id,
                tool: p.tool || 'mcp_invoke',
                args: p.args,
              }
            } else if (p.phase === 'result') {
              this.pendingPermission = null
            }
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
            }
            flushBubble()
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
        this.pendingPermission = null
      }
    },
    async send(text: string) {
      if (!text.trim()) return
      if (this.isStreaming) return
      if (this.streamingSessionId !== null && this.streamingSessionId === this.sessionId) return
      // 旧的 pending 审批卡片自动取消（新一轮对话开始）
      for (const m of this.messages) {
        if (m.planApproval?.status === 'pending') {
          m.planApproval.status = 'cancelled'
        }
      }
      const userMsg: Msg = { id: 'u-' + String(Date.now()), role: 'user', content: text }
      const asstMsg: Msg = { id: 'a-' + String(Date.now() + 1), role: 'assistant', content: '' }
      this.messages.push(userMsg, asstMsg)
      this.isStreaming = true
      this.streamingSessionId = this.sessionId
      this.streamingMessageId = asstMsg.id
      this.error = null
      this.stage = null
      this.abortCtl = new AbortController()

      const payload = this._buildPayload(text)

      // HITL 计划审批关闭：行为与原来完全一致
      if (!this.planApproval) {
        await this._runStream(asstMsg, payload)
        return
      }

      // 阶段 1：只读预览计划（router + planner），不写会话
      try {
        const res = await planPreview(payload, this.abortCtl?.signal)
        if (!res.needs_plan || !res.steps?.length) {
          // 非研究意图 / 规划失败：走正常流（无 override）
          await this._runStream(asstMsg, payload)
          return
        }
        // 计划待审批：挂起卡片，恢复输入框交互
        asstMsg.planApproval = { status: 'pending', summary: res.plan_summary || '', steps: res.steps }
        const idx = this.messages.findIndex(m => m.id === asstMsg.id)
        if (idx >= 0) this.messages[idx] = { ...asstMsg }
        this._endStreaming()
      } catch (e) {
        if (this.abortCtl?.signal.aborted) {
          this._endStreaming()
          return
        }
        // preview 失败：降级为无审批的正常流（规划永不阻塞主流程）
        await this._runStream(asstMsg, payload)
      }
    },
    /** HITL 阶段 2：用户批准（可编辑后）计划，带 plan_override 走正常 SSE 流 */
    async approvePlan(msgId: string, steps: string[], summary: string) {
      if (this.isStreaming) return
      const i = this.messages.findIndex(m => m.id === msgId)
      if (i < 0) return
      const msg = this.messages[i]
      if (msg.planApproval?.status !== 'pending') return
      const cleaned = steps.map(s => s.trim()).filter(Boolean)
      if (!cleaned.length) return
      // 配对的用户消息（assistant 前一条 user）
      const prev = this.messages[i - 1]
      if (!prev || prev.role !== 'user') return

      // 卡片 -> 进度条过渡
      msg.planApproval = undefined
      this.messages[i] = { ...msg }
      // 恢复流式状态
      this.isStreaming = true
      this.streamingSessionId = this.sessionId
      this.streamingMessageId = msgId
      this.error = null
      this.stage = null
      this.abortCtl = new AbortController()

      const payload = this._buildPayload(prev.content, {
        use_planner: true,
        plan_override: { summary, steps: cleaned },
      })
      await this._runStream(msg, payload)
    },
    /** HITL：取消待审批的计划（保留用户消息和已取消卡片，本轮不入库） */
    cancelPlan(msgId: string) {
      const i = this.messages.findIndex(m => m.id === msgId)
      if (i < 0) return
      const msg = this.messages[i]
      if (msg.planApproval?.status !== 'pending') return
      msg.planApproval.status = 'cancelled'
      this.messages[i] = { ...msg }
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
