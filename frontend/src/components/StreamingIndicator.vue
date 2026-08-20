<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'

const chat = useChatStore()
const sessions = useSessionsStore()
const router = useRouter()

// Only when a stream is running AND the user is NOT looking at the session
// that's producing. (When the user IS on the streaming session, ChatView's own
// inline thinking row already shows the same info.)
const visible = computed<boolean>(() => {
  return (
    chat.isStreaming &&
    chat.streamingSessionId !== null &&
    chat.streamingSessionId !== chat.sessionId
  )
})

const targetSession = computed(() => {
  if (!chat.streamingSessionId) return null
  return sessions.items.find(s => s.id === chat.streamingSessionId) || null
})

const label = computed<string>(() => {
  const s = chat.stage
  if (!s) return '思考中...'
  if (s.stage === 'rag_search' && s.status === 'started') return '检索知识库中...'
  if (s.stage === 'rag_search' && s.status === 'done') {
    return s.hits && s.hits > 0 ? '生成回答中...' : '生成回答中...'
  }
  if (s.stage === 'llm_stream' && s.status === 'started') return '生成回答中...'
  return '思考中...'
})

const elapsed = ref(0)
let timerId: number | null = null
function startTimer() {
  stopTimer()
  elapsed.value = 0
  timerId = window.setInterval(() => { elapsed.value++ }, 1000)
}
function stopTimer() {
  if (timerId !== null) { window.clearInterval(timerId); timerId = null }
}

watch(visible, (v) => {
  if (v) startTimer()
  else { stopTimer(); elapsed.value = 0 }
}, { immediate: true })

onBeforeUnmount(stopTimer)

function switchTo() {
  if (chat.streamingSessionId) {
    router.push({ name: 'chat-id', params: { id: chat.streamingSessionId } })
  }
}
</script>

<template>
  <Transition name="slide-up">
    <div v-if="visible" class="streaming-indicator" @click="switchTo" role="button" tabindex="0">
      <div class="indicator-icon" aria-hidden="true">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
      <div class="indicator-content">
        <div class="indicator-title">{{ targetSession?.title || '未命名会话' }}</div>
        <div class="indicator-status">{{ label }}（{{ elapsed }}s）· 点击切回去</div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.streaming-indicator {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--bg-bubble-assistant, #2a2a2a);
  color: var(--text-primary, #fff);
  padding: 10px 14px;
  border-radius: 12px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 320px;
  z-index: 1000;
  user-select: none;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
}
.streaming-indicator:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.22);
}
.streaming-indicator:focus { outline: none; }
.streaming-indicator:focus-visible {
  outline: 2px solid var(--accent, #3b82f6);
  outline-offset: 2px;
}

.indicator-icon {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
}
.dot {
  width: 6px;
  height: 6px;
  background: var(--accent, #3b82f6);
  border-radius: 50%;
  animation: bounce 1.2s ease-in-out infinite;
}
.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.3s; }
@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
  40% { transform: translateY(-4px); opacity: 1; }
}

.indicator-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.indicator-title {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}
.indicator-status {
  font-size: 12px;
  opacity: 0.7;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(16px);
}
</style>
