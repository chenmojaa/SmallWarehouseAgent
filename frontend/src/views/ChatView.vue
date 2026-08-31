<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'
import { useModelsStore } from '@/stores/models'
import { NSpace, NInput, NButton, NText, NSwitch } from 'naive-ui'
import MessageBubble from '@/components/MessageBubble.vue'
import ThinkingIndicator from '@/components/ThinkingIndicator.vue'
import ModelSelector from '@/components/ModelSelector.vue'
import CitationPreview from '@/components/CitationPreview.vue'
import IngestResultCard from '@/components/IngestResultCard.vue'

const chat = useChatStore()
const sessions = useSessionsStore()
const models = useModelsStore()
const route = useRoute()


const input = ref("")
const scrollRef = ref<HTMLElement | null>(null)

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
  loadByRoute()
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
          <div class="rag-group">
            <span class="rag-label">知识库</span>
            <NSwitch :value="chat.useRag" @update:value="chat.toggleRag()" size="small" />
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
          <div class="rag-group">
            <span class="rag-label">知识库</span>
            <NSwitch :value="chat.useRag" @update:value="chat.toggleRag()" size="small" />
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
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  gap: 12px;
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
</style>
