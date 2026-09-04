<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'
import { useModelsStore } from '@/stores/models'
import { NSpace, NInput, NButton, NText, NSwitch, NModal, NSelect } from 'naive-ui'
import MessageBubble from '@/components/MessageBubble.vue'
import ThinkingIndicator from '@/components/ThinkingIndicator.vue'
import ModelSelector from '@/components/ModelSelector.vue'
import CitationPreview from '@/components/CitationPreview.vue'
import IngestResultCard from '@/components/IngestResultCard.vue'
import PlanApprovalCard from '@/components/PlanApprovalCard.vue'
import { t } from '@/i18n'

const chat = useChatStore()
const sessions = useSessionsStore()
const models = useModelsStore()
const route = useRoute()


const input = ref("")
const scrollRef = ref<HTMLElement | null>(null)

// Agent 本地访问权限模式下拉选项：完全访问为红色警示
const permissionOptions = computed(() => [
  { label: '默认权限', value: 'default' },
  { label: '完全访问', value: 'full', class: 'perm-option-danger' },
])

// 选择完全访问时先弹窗确认
const confirmFullOpen = ref(false)
function onPermissionChange(v: string) {
  if (v === 'full') {
    confirmFullOpen.value = true   // 先弹确认框，确认后再真正切换
    return
  }
  chat.setAgentPermission('default')
}
function confirmFullAccess() {
  chat.setAgentPermission('full')
  confirmFullOpen.value = false
}

// === 消息操作 ===
const clickedAct = ref('')
let clickedTimer: number | undefined
function flashAct(name: string) {
  clickedAct.value = name
  if (clickedTimer) window.clearTimeout(clickedTimer)
  clickedTimer = window.setTimeout(() => { clickedAct.value = '' }, 800)
}
async function copyMsg(m: { content: string }): Promise<void> {
  try {
    await navigator.clipboard.writeText(m.content || '')
    flashAct('copy')
  } catch { /* clipboard 不可用时静默失败 */ }
}
function formatMsgTime(id: string): string {
  // 从消息 id（如 u-1725100000000）中提取时间戳
  const ts = parseInt(id.replace(/^[ua]-/, ''), 10)
  if (isNaN(ts)) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function loadByRoute() {
  const id = route.params.id as string | undefined
  if (id) {
    await chat.loadFromSession(id)
  } else {
    chat.clear()
  }
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

onMounted(() => {
  sessions.load()
  loadByRoute().then(() => {
    // MCP 页面「发起试试」：跳转过来后自动发送暂存的问题
    const q = sessionStorage.getItem('mcp-quick-prompt')
    if (q) {
      sessionStorage.removeItem('mcp-quick-prompt')
      if (!chat.streamingHere) chat.send(q).then(() => {
        nextTick(() => { if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight })
        sessions.load()
      })
    }
  })
})
watch(() => route.params.id, loadByRoute)

async function send() {
  const text = input.value.trim()
  if (!text || chat.streamingHere) return
  input.value = ""
  await chat.send(text)
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  sessions.load()
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div v-if="chat.error && !chat.isStreaming" class="load-error">
    <span>{{ chat.error }}</span>
    <n-button size="tiny" quaternary @click="loadByRoute">重试</n-button>
  </div>
  <!-- 空对话时：用 welcome 布局把问候语 + 输入框一起垂直居中上半屏 -->
  <div v-if="chat.messages.length === 0" class="welcome-layout">
    <div class="welcome">
      <div class="welcome-text">嗨，有什么我可以帮助你的？</div>
    </div>
    <div class="chat-container input-container-welcome">
      <div class="input-bar">
        <n-input
          v-model:value="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 10 }"
          placeholder="输入消息，回车发送，Shift+Enter 换行"
          @keydown="onKey"
          class="chat-input"
          :bordered="false"
        />
        <div class="input-toolbar">
          <button
            type="button"
            class="plan-toggle"
            :class="{ on: chat.usePlanner }"
            :title="chat.usePlanner ? '任务规划已开启：复杂问题会先分解为检索计划再执行' : '任务规划已关闭：直接检索，不分解子查询'"
            @click="chat.togglePlanner()"
          >
            <span>Plan</span>
          </button>
          <button
            type="button"
            class="plan-toggle"
            :class="{ on: chat.planApproval }"
            :title="chat.planApproval
              ? t('chat.planApproval.tip.on', '计划审批已开启：研究任务先生成计划，你确认后才执行', 'Plan approval ON: research tasks wait for your review before running')
              : t('chat.planApproval.tip.off', '计划审批已关闭：计划自动执行', 'Plan approval OFF: plans run automatically')"
            @click="chat.togglePlanApproval()"
          >
            <span>{{ t('chat.planApproval.toggle', '审批', 'Approve') }}</span>
          </button>
          <div class="rag-group">
            <span class="rag-label">知识库</span>
            <NSwitch :value="chat.useRag" @update:value="chat.toggleRag()" size="small" />
          </div>
          <div class="rag-group perm-group" :title="chat.agentPermission === 'full' ? '完全访问：Agent 可直接访问本机磁盘，不再询问' : '默认权限：Agent 访问本地文件前会先询问你'">
            <n-select
              :value="chat.agentPermission ?? 'default'"
              :options="permissionOptions"
              size="tiny"
              class="perm-select"
              :class="{ 'perm-full': chat.agentPermission === 'full' }"
              placeholder="默认权限"
              @update:value="onPermissionChange"
            />
          </div>
          <div style="flex: 1; min-width: 0"></div>
          <ModelSelector />
          <n-button class="send-btn" type="primary" :disabled="chat.streamingHere" @click="send" circle>
            <template #icon>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="19" x2="12" y2="5"/>
                <polyline points="5 12 12 5 19 12"/>
              </svg>
            </template>
          </n-button>
        </div>
      </div>
      <div class="footer-hint">
        <span class="hint-icon">📨</span>
        <span>有问题尽管问，开启后会检索你的知识库回答</span>
      </div>
    </div>
  </div>

  <!-- 有对话时：正常聊天布局，输入框贴底 -->
  <div v-else class="chat-page">
    <div ref="scrollRef" class="chat-scroll">
      <div class="chat-container">
        <div v-for="m in chat.messages" :key="m.id" :class="['msg-row', 'msg-' + m.role]">
          <!-- HITL 计划审批卡片：待批准/已取消（approved 后由 plan-strip 接管） -->
          <PlanApprovalCard
            v-if="m.role === 'assistant' && m.planApproval && m.planApproval.status !== 'approved'"
            :summary="m.planApproval.summary"
            :steps="m.planApproval.steps"
            :status="m.planApproval.status"
            :disabled="chat.isStreaming"
            @run="(steps: string[]) => chat.approvePlan(m.id, steps, m.planApproval?.summary || '')"
            @cancel="chat.cancelPlan(m.id)"
          />
          <!-- 任务规划进度条：计划步骤 pending/running/done + 命中数 -->
          <div v-if="m.role === 'assistant' && m.planSteps && m.planSteps.length" class="plan-strip">
            <div class="plan-head">
              <span class="plan-label">检索计划</span>
              <span v-if="m.planSummary" class="plan-summary">{{ m.planSummary }}</span>
            </div>
            <div class="plan-steps">
              <span
                v-for="(s, i) in m.planSteps"
                :key="i"
                class="plan-chip"
                :class="[s.status, { replan: s.replan }]"
                :title="s.query + (s.hits != null ? '（命中 ' + s.hits + ' 条）' : '')"
              >
                <span v-if="s.status === 'running'" class="tool-spin">◌</span>
                <span v-else-if="s.status === 'done'" class="tool-ok">{{ s.replan ? '+' : '✓' }}</span>
                <span v-else class="plan-pending-num">{{ i + 1 }}</span>
                <span class="plan-chip-query">{{ s.replan ? '补检索：' : '' }}{{ s.query.length > 18 ? s.query.slice(0, 18) + '…' : s.query }}</span>
                <span v-if="s.status === 'done' && s.hits != null" class="plan-chip-hits">{{ s.hits }}</span>
              </span>
            </div>
          </div>
          <!-- 工具调用进度条：MCP / 技能工具的 running -> ok/failed 状态 -->
          <div v-if="m.role === 'assistant' && m.toolCalls && m.toolCalls.length" class="tool-strip">
            <span
              v-for="(t, i) in m.toolCalls" :key="i"
              class="tool-chip" :class="t.status"
              :title="t.snippet"
            >
              <span v-if="t.status === 'running'" class="tool-spin">◌</span>
              <span v-else-if="t.status === 'ok'" class="tool-ok">✓</span>
              <span v-else class="tool-fail">✕</span>
              {{ t.name }}
            </span>
          </div>
          <!-- Render the bubble as soon as ANY content exists (including a
               partial <think> block) so the collapsible thinking section is
               visible and live-updating during the whole stream. The
               ThinkingIndicator placeholder only covers the empty-content
               gap before the first token arrives. -->
          <template v-if="!(chat.streamingHere && m.id === chat.streamingMessageId && !m.content.trim())">
            <MessageBubble
              :role="m.role"
              :content="m.content"
              :citations="m.citations"
              :active-index="m.activeCitationIndex ?? null"
              @update:active-index="(n: number) => chat.setActiveCitation(m.id, n <= 0 ? null : n)"
            />
          </template>
          <template v-else-if="chat.streamingHere && m.id === chat.streamingMessageId">
            <ThinkingIndicator :show="true" />
          </template>
          <div v-if="m.role !== 'system'" class="msg-actions">
            <span class="msg-time">{{ formatMsgTime(m.id) }}</span>
            <button class="msg-act" type="button" title="复制" :class="{ clicked: clickedAct === 'copy' }" @click="copyMsg(m)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button v-if="m.role === 'assistant'" class="msg-act" type="button" title="重新生成" :class="{ clicked: clickedAct === 'regen' }" @click="chat.regenerate(); flashAct('regen')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
            <button class="msg-act" type="button" title="删除" :class="{ clicked: clickedAct === 'delete' }" @click="chat.deleteMessage(m.id); flashAct('delete')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
            </button>
            <button class="msg-act" type="button" title="回退" :class="{ clicked: clickedAct === 'undo' }" @click="chat.undoLast(); flashAct('undo')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
            </button>
          </div>
          <CitationPreview
            v-if="m.role === 'assistant' && m.citations && m.citations.length > 0 && m.activeCitationIndex != null && m.activeCitationIndex >= 1 && m.citations[m.activeCitationIndex - 1]"
            class="citations-row"
            :citation="m.citations[m.activeCitationIndex - 1]"
            :index="m.activeCitationIndex"
            @close="chat.setActiveCitation(m.id, null)"
          />
          <IngestResultCard v-if="m.role === 'assistant' && m.ingest" :data="m.ingest" class="ingest-row" />
          <div v-if="m.role === 'assistant' && m.report" class="report-row">
            <div class="report-head">周报已生成</div>
            <div v-if="m.report.message" class="report-msg">{{ m.report.message }}</div>
            <div v-else-if="m.report.summary" class="report-summary">{{ m.report.summary }}</div>
            <div v-if="m.report.note_id" class="report-meta">已存为笔记 #{{ m.report.note_id.slice(0, 8) }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-container input-container">
      <div class="input-bar">
        <n-input
          v-model:value="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 10 }"
          placeholder="输入消息，回车发送，Shift+Enter 换行"
          @keydown="onKey"
          class="chat-input"
          :bordered="false"
        />
        <div class="input-toolbar">
          <button
            type="button"
            class="plan-toggle"
            :class="{ on: chat.usePlanner }"
            :title="chat.usePlanner ? '任务规划已开启：复杂问题会先分解为检索计划再执行' : '任务规划已关闭：直接检索，不分解子查询'"
            @click="chat.togglePlanner()"
          >
            <span>Plan</span>
          </button>
          <button
            type="button"
            class="plan-toggle"
            :class="{ on: chat.planApproval }"
            :title="chat.planApproval
              ? t('chat.planApproval.tip.on', '计划审批已开启：研究任务先生成计划，你确认后才执行', 'Plan approval ON: research tasks wait for your review before running')
              : t('chat.planApproval.tip.off', '计划审批已关闭：计划自动执行', 'Plan approval OFF: plans run automatically')"
            @click="chat.togglePlanApproval()"
          >
            <span>{{ t('chat.planApproval.toggle', '审批', 'Approve') }}</span>
          </button>
          <div class="rag-group">
            <span class="rag-label">知识库</span>
            <NSwitch :value="chat.useRag" @update:value="chat.toggleRag()" size="small" />
          </div>
          <div class="rag-group perm-group" :title="chat.agentPermission === 'full' ? '完全访问：Agent 可直接访问本机磁盘，不再询问' : '默认权限：Agent 访问本地文件前会先询问你'">
            <n-select
              :value="chat.agentPermission ?? 'default'"
              :options="permissionOptions"
              size="tiny"
              class="perm-select"
              :class="{ 'perm-full': chat.agentPermission === 'full' }"
              placeholder="默认权限"
              @update:value="onPermissionChange"
            />
          </div>
          <div style="flex: 1; min-width: 0"></div>
          <ModelSelector />
          <n-button class="send-btn" type="primary" :disabled="chat.streamingHere" @click="send" circle>
            <template #icon>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="19" x2="12" y2="5"/>
                <polyline points="5 12 12 5 19 12"/>
              </svg>
            </template>
          </n-button>
        </div>
      </div>
    </div>
  </div>

  <!-- 权限审批弹窗：默认权限模式下 Agent 请求访问本地文件时弹出 -->
  <n-modal :show="!!chat.pendingPermission" @update:show="(v: boolean) => { if (!v) chat.resolvePermission(false) }" :mask-closable="false">
    <div v-if="chat.pendingPermission" class="perm-dialog">
      <div class="perm-dialog-icon">🔐</div>
      <h3 class="perm-dialog-title">助手请求访问本地资源</h3>
      <p class="perm-dialog-desc">助手正在「默认权限」模式下运行，执行以下操作前需要你的确认：</p>
      <div class="perm-dialog-detail">
        <div class="perm-row"><span class="perm-k">工具</span><code>{{ chat.pendingPermission.tool }}</code></div>
        <div class="perm-row"><span class="perm-k">参数</span><code class="perm-args">{{ JSON.stringify(chat.pendingPermission.args, null, 2) }}</code></div>
      </div>
      <div class="perm-dialog-actions">
        <n-button @click="chat.resolvePermission(false)">拒绝</n-button>
        <n-button type="primary" @click="chat.resolvePermission(true)">允许本次访问</n-button>
      </div>
      <p class="perm-dialog-hint">如不想每次确认，可在输入框下方开启「完全访问」权限</p>
    </div>
  </n-modal>

  <!-- 开启完全访问的二次确认弹窗 -->
  <n-modal :show="confirmFullOpen" @update:show="(v: boolean) => { if (!v) confirmFullOpen = false }" :mask-closable="false">
    <div class="perm-dialog perm-confirm-dialog">
      <h3 class="perm-dialog-title">⚠️ 确认开启完全访问？</h3>
      <p class="perm-dialog-desc">开启后，<strong>Agent 可以直接读写本机所有磁盘的文件</strong>，执行操作前<strong class="danger-text">不再询问你</strong>。请确认你了解其中的风险。可随时切回「默认权限」恢复逐次确认。</p>
      <div class="perm-dialog-actions">
        <n-button @click="confirmFullOpen = false">取消</n-button>
        <n-button type="error" @click="confirmFullAccess">我已了解，开启完全访问</n-button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chat-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.chat-container {
  max-width: 1100px;
  width: 90%;
  margin: 0 auto;
  padding: 0 24px;
}
.input-container {
  padding: 8px 16px 10px;
  flex-shrink: 0;
}

/* ====== 空对话专属：紧凑上半屏布局 ====== */
.welcome-layout {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 22px;
  padding: 0 16px;
  overflow-y: auto;
}
.welcome-layout { padding-top: calc(50vh - 180px); }
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 6px;
}
.welcome-text {
  font-size: 22px;
  font-weight: 500;
  color: var(--text-primary);
  opacity: 0.9;
  line-height: 1.4;
}
.input-container-welcome {
  flex-shrink: 0;
}

/* ====== 消息行（聊天态） ====== */
.msg-row { margin-bottom: 12px; }

/* 权限下拉框（知识库开关旁） */
.perm-group { gap: 6px; }
.perm-select { width: 108px; }
.perm-select :deep(.n-base-selection) { border-radius: 8px; }
/* 完全访问激活态：红色警示文字 */
.perm-select.perm-full :deep(.n-base-selection-input) { color: #ef4444; font-weight: 600; }
/* 下拉选项「完全访问」红色 */
:global(.perm-option-danger) { color: #ef4444 !important; font-weight: 600; }

/* 确认弹窗危险色 */
.perm-dialog-icon.danger { filter: none; }
.danger-text { color: #ef4444; }

/* 权限审批弹窗 */
.perm-dialog {
  width: min(440px, calc(100vw - 48px));
  background: var(--bg-elevated, #fff);
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.perm-dialog-icon { font-size: 30px; text-align: center; }
.perm-dialog-title { margin: 0; text-align: center; font-size: 17px; color: var(--text-primary, #222); }
.perm-dialog-desc { margin: 0; font-size: 13px; color: var(--text-secondary, #888); text-align: center; }
.perm-dialog-detail {
  border: 1px solid var(--border-soft, rgba(128, 128, 128, 0.2));
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-app, rgba(128, 128, 128, 0.05));
}
.perm-row { display: flex; gap: 10px; align-items: flex-start; font-size: 12px; }
.perm-k { color: var(--text-muted, #999); flex-shrink: 0; min-width: 32px; padding-top: 2px; }
.perm-row code { word-break: break-all; color: var(--text-primary, #333); }
.perm-args { max-height: 140px; overflow-y: auto; white-space: pre-wrap; }
.perm-dialog-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.perm-dialog-actions :deep(.n-button) { border-radius: 10px; }
.perm-dialog-hint { margin: 0; font-size: 11px; color: var(--text-muted, #aaa); text-align: center; }

/* 工具调用进度条：助手消息上方的 MCP/技能工具状态 chips */
.tool-strip { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.tool-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 999px;
  font-size: 12px; color: var(--text-secondary, #aaa);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  background: var(--bg-elevated, rgba(255, 255, 255, 0.04));
  max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tool-chip.running .tool-spin { display: inline-block; animation: toolSpin 1s linear infinite; color: var(--brand-blue, #3b82f6); }
.tool-chip.ok .tool-ok { color: #4ade80; }
.tool-chip.failed { color: #f87171; border-color: rgba(248, 113, 113, 0.35); }
.tool-chip.failed .tool-fail { color: #f87171; }
@keyframes toolSpin { to { transform: rotate(360deg); } }

/* Plan 开关按钮：输入框工具栏左侧，开启高亮 / 关闭置灰 */
.plan-toggle {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 500; line-height: 18px;
  color: var(--text-muted, #888);
  border: 1px solid var(--border-soft, rgba(128, 128, 128, 0.25));
  background: transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.plan-toggle:hover { color: var(--text-secondary, #aaa); }
.plan-toggle.on {
  color: var(--brand-blue, #3b82f6);
  border-color: rgba(59, 130, 246, 0.45);
  background: rgba(59, 130, 246, 0.10);
}

/* 任务规划进度条：计划摘要 + 步骤 chips（复用 tool-chip 风格） */
.plan-strip {
  display: flex; flex-direction: column; gap: 6px;
  margin-bottom: 6px;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  background: var(--bg-elevated, rgba(255, 255, 255, 0.04));
  max-width: 520px;
}
.plan-head { display: flex; align-items: baseline; gap: 8px; }
.plan-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.4px;
  color: var(--brand-blue, #3b82f6);
  flex-shrink: 0;
}
.plan-summary {
  font-size: 12px; color: var(--text-secondary, #aaa);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.plan-steps { display: flex; flex-wrap: wrap; gap: 6px; }
.plan-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 999px;
  font-size: 12px; color: var(--text-secondary, #aaa);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  background: var(--bg-elevated, rgba(255, 255, 255, 0.04));
  max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.plan-chip.running { color: var(--brand-blue, #3b82f6); border-color: rgba(59, 130, 246, 0.4); }
.plan-chip.running .tool-spin { display: inline-block; animation: toolSpin 1s linear infinite; }
.plan-chip.done .tool-ok { color: #4ade80; }
.plan-chip.replan { border-style: dashed; }
.plan-pending-num { font-size: 11px; color: var(--text-muted, #777); }
.plan-chip-query { overflow: hidden; text-overflow: ellipsis; }
.plan-chip-hits {
  font-size: 11px; color: #4ade80;
  font-variant-numeric: tabular-nums;
}

/* 消息操作栏：悬浮消息行时显示，位于气泡下方 */
.msg-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.15s;
  pointer-events: none;
}
.msg-row:hover .msg-actions {
  opacity: 1;
  pointer-events: auto;
}
/* 用户消息的操作栏靠右对齐，模型消息靠左 */
.msg-user .msg-actions { justify-content: flex-end; }
.msg-assistant .msg-actions { justify-content: flex-start; }
.msg-time {
  font-size: 11px;
  color: var(--text-muted, #888);
  margin-right: 6px;
  user-select: none;
}
.msg-act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted, #888);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.msg-act:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.06));
  color: var(--text-primary);
}
.msg-act.clicked {
  color: var(--accent, #3b82f6);
  background: rgba(59, 130, 246, 0.12);
  animation: msg-act-pop 0.35s ease;
}
@keyframes msg-act-pop {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.25); }
  100% { transform: scale(1); }
}

.citations-row { margin-top: 6px; }
.ingest-row { margin-top: 6px; }
.report-row {
  margin-top: 6px;
  padding: 10px 14px;
  background: var(--bg-bubble-assistant);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  border-left: 3px solid #10b981;
  border-radius: 8px;
  font-size: 13px;
  max-width: 560px;
}
.report-head { font-weight: 600; margin-bottom: 4px; }
.report-msg,
.report-summary {
  color: var(--text-secondary, #aaa);
  white-space: pre-wrap;
  line-height: 1.55;
}
.report-meta {
  margin-top: 4px;
  color: var(--text-tertiary, #888);
  font-size: 12px;
  font-family: monospace;
}

/* ====== 输入栏：大圆角 + 柔和阴影 + 内部组件无边框 ====== */
.input-bar {
  padding: 8px 12px;
  background: var(--bg-input-bar);
  border: 1px solid var(--border-input-bar);
  border-radius: 22px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.input-bar:focus-within {
  border-color: var(--input-border-hover);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.chat-input { width: 100%; }
.chat-input :deep(.n-input-wrapper) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 4px 4px !important;
}
.chat-input :deep(.n-input) {
  padding: 0 !important;
  border-radius: 16px !important;
}
.chat-input :deep(.n-input__textarea-el) {
  padding: 4px 4px !important;
  margin: 0 !important;
  text-indent: 0 !important;
  resize: none !important;
  border-radius: 16px !important;
}
.chat-input :deep(.n-input__textarea-el::placeholder) {
  text-indent: 0 !important;
  padding-left: 0 !important;
  transition: opacity 0.15s ease;
}
.input-bar:focus-within .chat-input :deep(.n-input__textarea-el::placeholder) {
  opacity: 0;
}
.input-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 6px;
  gap: 8px;
  padding: 0 4px;
}
.model-picker-wrap :deep(.n-select .n-base-selection),
.model-picker-wrap :deep(.n-select .n-base-selection:hover) {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
.rag-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  height: 32px;
}
.rag-label {
  font-size: 12px;
  opacity: 0.7;
  white-space: nowrap;
}
/* RAG 开关显式可见样式 */
.rag-group :deep(.n-switch) {
  min-width: 32px;
  min-height: 18px;
}
.rag-group :deep(.n-switch__rail) {
  background-color: var(--border-input-bar) !important;
}
.rag-group :deep(.n-switch--active .n-switch__rail) {
  background-color: #3b82f6 !important;
}
.rag-group :deep(.n-switch__button) {
  background-color: #ffffff !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15) !important;
}


.send-btn { width: 32px; height: 32px; padding: 0; }
.send-btn:not(.n-button--disabled-type) { background: #3b82f6; color: #ffffff; }
.send-btn.n-button--disabled-type {
  background: #3f3f46 !important;
  color: #a1a1aa !important;
  cursor: not-allowed;
  opacity: 1 !important;
}
.send-btn.n-button--disabled-type .n-button__content { color: #a1a1aa !important; }

.footer-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
  opacity: 0.65;
}
.hint-icon { font-size: 13px; }
.load-error {
  position: absolute;
  top: 12px;
  right: 16px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: min(520px, calc(100% - 32px));
  padding: 8px 10px;
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.12);
  color: #fca5a5;
  font-size: 12px;
}

.drop-overlay {
  position: fixed; inset: 0;
  background: rgba(59, 130, 246, 0.18);
  backdrop-filter: blur(4px);
  z-index: 5000;
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drop-card {
  background: var(--bg-app, #1f1f23);
  border: 2px dashed #3b82f6;
  border-radius: 14px;
  padding: 36px 56px;
  text-align: center;
  box-shadow: 0 16px 40px rgba(0,0,0,0.4);
}
.drop-icon { font-size: 48px; margin-bottom: 8px; }
.drop-title { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
.drop-sub { font-size: 13px; color: var(--text-muted, #888); }
.drop-fade-enter-active, .drop-fade-leave-active { transition: opacity 0.12s; }
.drop-fade-enter-from, .drop-fade-leave-to { opacity: 0; }

</style>
