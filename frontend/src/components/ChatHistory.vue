<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionsStore } from '@/stores/sessions'
import { useChatStore } from '@/stores/chat'
import { useModelsStore } from '@/stores/models'
import { NButton, NPopconfirm, NEmpty, NSpin, NText, NModal, NSpace, NInput } from 'naive-ui'

const sessions = useSessionsStore()
const chat = useChatStore()
const models = useModelsStore()
const route = useRoute()
const router = useRouter()

const activeId = computed(() => (route.params.id as string) || null)

async function newChat() {
  chat.clear()
  router.push({ name: 'chat' })
}

function gotoNotes() {
  router.push({ name: 'notes' })
}

function gotoSkillsMcp() {
  router.push({ name: 'skills-mcp' })
}

async function openSession(id: string) {
  if (id === activeId.value) {
    // Same session re-clicked: force a reload so the UI always reflects latest server state.
    await chat.loadFromSession(id)
    return
  }
  router.push({ name: 'chat-id', params: { id } })
}

function retryInitialLoad() {
  sessions.load()
  models.loadFromBackend()
}

async function removeSession(id: string, e: Event) {
  e.stopPropagation()
  await sessions.remove(id)
  if (activeId.value === id) {
    chat.clear()
    router.push({ name: 'chat' })
  }
}

function fmt(s: string) {
  try { return new Date(s).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
  catch { return s }
}

// === Search dialog ===
const searchOpen = ref(false)
const searchQuery = ref("")
const searchedSessions = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return sessions.items
  return sessions.items.filter((s: any) => {
    const title = (s.title || "").toLowerCase()
    const preview = (s.preview || "").toLowerCase()
    return title.includes(q) || preview.includes(q)
  })
})

function openSearch() { searchQuery.value = ""; searchOpen.value = true }
function pickSession(id: string) { searchOpen.value = false; router.push({ name: "chat-id", params: { id } }) }
</script>

<template>
  <div class="chat-history">
    <div class="chat-history-actions">
      <n-button block quaternary @click="newChat" class="action-btn new-chat-btn">+ 新对话</n-button>
      <n-button block quaternary @click="gotoNotes" class="action-btn">知识库</n-button>
      <n-button block quaternary @click="openSearch" class="action-btn">搜索对话</n-button>
      <n-button block quaternary @click="gotoSkillsMcp" class="action-btn">技能 · MCP</n-button>
    </div>
    <div class="chat-history-header">
      <span class="title">历史记录</span>
    </div>
    <div class="chat-history-list">
      <div v-if="sessions.loading && sessions.items.length === 0" class="loading-row">
        <n-spin size="small" />
        <n-text depth="3" style="font-size: 12px">加载中…</n-text>
      </div>
      <template v-else-if="sessions.items.length > 0">
        <button v-if="sessions.error" class="stale-retry" type="button" @click="retryInitialLoad">
          已显示缓存 · 加载失败，点击重试
        </button>
        <div
          v-for="s in sessions.items"
          :key="s.id"
          @click="openSession(s.id)"
          :class="['session-item', s.id === activeId ? 'active' : '']"
        >
          <div class="session-row">
            <span class="session-title">{{ s.title }}</span>
            <n-popconfirm @positive-click="removeSession(s.id, $event)">
              <template #trigger>
                <n-button text size="small" type="error" @click.stop class="delete-btn">✕</n-button>
              </template>
              删除该对话？
            </n-popconfirm>
          </div>
          <div v-if="s.preview" class="session-preview">{{ s.preview }}</div>
          <div class="session-meta">{{ fmt(s.updated_at) }} · {{ s.message_count }} 条</div>
        </div>
      </template>
      <n-empty v-else-if="sessions.error" size="small" description="历史记录加载失败" style="padding: 24px 0">
        <template #extra>
          <n-button size="small" @click="retryInitialLoad">重试</n-button>
        </template>
      </n-empty>
      <n-empty v-else size="small" description="点击 + 新对话 开始" style="padding: 24px 0" />
    </div>
  </div>
  <!-- 搜索对话 -->
  <n-modal v-model:show="searchOpen" preset="card" title="搜索对话" style="max-width: 480px">
    <n-input v-model:value="searchQuery" placeholder="搜索会话标题或预览片段" clearable />
    <n-space vertical size="small" style="margin-top: 12px; max-height: 360px; overflow-y: auto">
      <n-empty v-if="!sessions.loading && searchedSessions.length === 0" description="没有匹配的对话" />
      <div
        v-for="s in searchedSessions"
        :key="s.id"
        @click="pickSession(s.id)"
        class="search-item"
      >
        <div class="search-title">{{ s.title }}</div>
        <div v-if="s.preview" class="search-preview">{{ s.preview }}</div>
        <div class="search-meta">{{ fmt(s.updated_at) }} · {{ s.message_count }} 条</div>
      </div>
    </n-space>
  </n-modal>

</template>

<style scoped>
.chat-history {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.chat-history-actions {
  padding: 10px 12px 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.action-btn {
  height: 36px;
  border: none !important;
  background: transparent !important;
  border-radius: 12px !important;
  --n-border-radius: 12px !important;
}
.action-btn :deep(.n-button__content) {
  justify-content: flex-start;
  width: 100%;
}
.action-btn:hover {
  background: var(--hover-bg) !important;
}
.new-chat-btn {
  font-weight: 600;
  border-radius: 12px !important;
}
.new-chat-btn:hover {
  background: var(--active-bg) !important;
}
.chat-history-header {
  padding: 18px 18px 10px;
  display: flex;
  align-items: center;
  border-top: 1px solid var(--border-soft);
  margin-top: 12px;
}
.chat-history-header .title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  text-transform: uppercase;
}
.chat-history-list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  padding: 8px 12px;
}
.loading-row {
  padding: 12px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.session-item {
  padding: 10px 12px;
  cursor: pointer;
  border-left: 3px solid transparent;
  border-bottom: 1px solid var(--border-soft);
  transition: background 0.15s;
}
.session-item:hover {
  background: var(--hover-bg);
}
.session-item.active {
  border-left-color: #3b82f6;
  background: var(--active-bg);
}
.session-item.active:hover {
  background: var(--active-bg-hover);
}
.session-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
}
.session-title {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  color: var(--text-primary);
}
.delete-btn {
  padding: 0 4px;
  font-size: 11px;
  flex-shrink: 0;
}
.session-preview {
  font-size: 11px;
  opacity: 0.6;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}
.session-meta {
  font-size: 10px;
  opacity: 0.4;
  margin-top: 4px;
  color: var(--text-muted);
}
.stale-retry {
  width: 100%;
  margin-bottom: 8px;
  padding: 6px 8px;
  border: 1px solid rgba(248, 113, 113, 0.35);
  border-radius: 6px;
  background: rgba(248, 113, 113, 0.08);
  color: #fca5a5;
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}
.search-item {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  cursor: pointer;
  transition: background 0.15s;
}
.search-item:hover { background: var(--hover-bg) }
.search-title { font-size: 13px; font-weight: 600; color: var(--text-primary) }
.search-preview { font-size: 12px; opacity: 0.7; margin-top: 4px; color: var(--text-secondary) }
.search-meta { font-size: 11px; opacity: 0.5; margin-top: 4px; color: var(--text-muted) }
</style>
