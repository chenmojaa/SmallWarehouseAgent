<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useSessionsStore } from '@/stores/sessions'
import { useModelsStore } from '@/stores/models'
import { useSettingsStore } from '@/stores/settings'
import { open as openPalette } from '@/composables/useCommandPalette'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()
const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const sessions = useSessionsStore()
const models = useModelsStore()
const settings = useSettingsStore()

const query = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const activeIdx = ref(0)

interface CommandItem {
  id: string
  title: string
  subtitle?: string
  emoji: string
  group: string
  keywords?: string
  run: () => void | Promise<void>
}

const items = computed<CommandItem[]>(() => {
  const list: CommandItem[] = [
    // navigation
    { id: 'nav.chat', title: '新对话', emoji: '💬', group: '导航', run: () => { chat.clear(); router.push('/chat') } },
    { id: 'nav.notes', title: '知识库', emoji: '📚', group: '导航', run: () => router.push('/notes') },
    { id: 'nav.skills', title: '技能 / MCP', emoji: '🧩', group: '导航', run: () => router.push('/mcp') },
    // theme
    { id: 'theme.dark', title: '切换深色主题', emoji: '🌙', group: '外观', run: () => { settings.setTheme('dark') } },
    { id: 'theme.light', title: '切换浅色主题', emoji: '☀️', group: '外观', run: () => { settings.setTheme('light') } },
    // rag / planner
    { id: 'toggle.rag', title: chat.useRag ? '关闭 RAG 检索' : '开启 RAG 检索', emoji: '🔍', group: '对话', run: () => chat.toggleRag() },
    { id: 'toggle.planner', title: chat.usePlanner ? '关闭任务规划' : '开启任务规划', emoji: '🧠', group: '对话', run: () => chat.togglePlanner() },
    // model selector
    { id: 'reload.models', title: '重新加载模型列表', emoji: '🔄', group: '模型', run: () => models.loadFromBackend() },
    // sessions
    { id: 'reload.sessions', title: '刷新会话列表', emoji: '🔄', group: '会话', run: () => sessions.load() },
  ]
  // append recent sessions
  for (const s of sessions.items.slice(0, 5)) {
    list.push({
      id: 'session.' + s.id,
      title: s.title || '无标题会话',
      subtitle: s.preview ? s.preview.slice(0, 60) : undefined,
      emoji: '💬',
      group: '最近会话',
      keywords: (s.title || '') + ' ' + (s.preview || ''),
      run: () => { router.push({ name: 'chat-id', params: { id: s.id } }) },
    })
  }
  return list
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(it => {
    const hay = (it.title + ' ' + (it.subtitle || '') + ' ' + (it.keywords || '') + ' ' + it.group).toLowerCase()
    return hay.includes(q)
  })
})

const grouped = computed(() => {
  const m = new Map<string, CommandItem[]>()
  for (const it of filtered.value) {
    if (!m.has(it.group)) m.set(it.group, [])
    m.get(it.group)!.push(it)
  }
  return Array.from(m.entries())
})

watch(query, () => { activeIdx.value = 0 })
watch(() => props.show, async (v) => {
  if (v) {
    query.value = ''
    activeIdx.value = 0
    await nextTick()
    inputRef.value?.focus()
  }
})

function flatList(): CommandItem[] {
  const out: CommandItem[] = []
  for (const [, arr] of grouped.value) out.push(...arr)
  return out
}

function activate(it: CommandItem) {
  emit('update:show', false)
  Promise.resolve(it.run()).catch(() => {})
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { emit('update:show', false); e.preventDefault(); return }
  if (e.key === 'ArrowDown') {
    activeIdx.value = Math.min(activeIdx.value + 1, flatList().length - 1)
    e.preventDefault()
  } else if (e.key === 'ArrowUp') {
    activeIdx.value = Math.max(activeIdx.value - 1, 0)
    e.preventDefault()
  } else if (e.key === 'Enter') {
    const list = flatList()
    if (list[activeIdx.value]) activate(list[activeIdx.value])
    e.preventDefault()
  }
}
</script>

<template>
  <teleport to="body">
    <transition name="cmd-fade">
      <div v-if="show" class="cmd-mask" @click.self="emit('update:show', false)">
        <div class="cmd-panel" role="dialog" aria-modal="true">
          <div class="cmd-input-row">
            <span class="cmd-search-icon">⌘K</span>
            <input
              ref="inputRef"
              v-model="query"
              class="cmd-input"
              type="text"
              placeholder="搜索命令、会话或操作…"
              @keydown="onKey"
            />
            <button class="cmd-close" @click="emit('update:show', false)" aria-label="关闭">×</button>
          </div>
          <div class="cmd-body">
            <div v-if="filtered.length === 0" class="cmd-empty">
              没有匹配的命令
            </div>
            <div v-for="[group, arr] in grouped" :key="group" class="cmd-group">
              <div class="cmd-group-label">{{ group }}</div>
              <button
                v-for="(it, gi) in arr"
                :key="it.id"
                class="cmd-item"
                :class="{ active: flatList().indexOf(it) === activeIdx }"
                @click="activate(it)"
                @mousemove="activeIdx = flatList().indexOf(it)"
              >
                <span class="cmd-emoji">{{ it.emoji }}</span>
                <span class="cmd-title">{{ it.title }}</span>
                <span v-if="it.subtitle" class="cmd-subtitle">{{ it.subtitle }}</span>
              </button>
            </div>
          </div>
          <div class="cmd-footer">
            <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
            <span><kbd>Enter</kbd> 执行</span>
            <span><kbd>Esc</kbd> 关闭</span>
            <span class="cmd-footer-spacer"></span>
            <span class="cmd-footer-brand">{{ filtered.length }} 个结果</span>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
.cmd-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 12vh;
}
.cmd-panel {
  width: min(640px, 92vw);
  max-height: 70vh;
  background: var(--bg-app, #1f1f23);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.12));
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.cmd-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
}
.cmd-search-icon {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: var(--text-muted, #888);
  padding: 2px 8px;
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.16));
  border-radius: 4px;
}
.cmd-input {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary, #fff);
  font-size: 15px;
  font-family: inherit;
}
.cmd-close {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted, #888);
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}
.cmd-close:hover { background: var(--hover-bg, rgba(255, 255, 255, 0.08)); }
.cmd-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.cmd-empty {
  padding: 36px 16px;
  text-align: center;
  color: var(--text-muted, #888);
  font-size: 13px;
}
.cmd-group { margin-bottom: 6px; }
.cmd-group-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-muted, #888);
  padding: 8px 12px 4px;
}
.cmd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary, #fff);
  text-align: left;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.1s;
}
.cmd-item.active,
.cmd-item:hover {
  background: var(--hover-bg, rgba(255, 255, 255, 0.08));
}
.cmd-item.active {
  background: rgba(59, 130, 246, 0.18);
}
.cmd-emoji { font-size: 16px; width: 20px; text-align: center; }
.cmd-title { flex-shrink: 0; }
.cmd-subtitle {
  flex: 1;
  text-align: right;
  font-size: 12px;
  color: var(--text-muted, #888);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cmd-footer {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  font-size: 11px;
  color: var(--text-muted, #888);
}
.cmd-footer-spacer { flex: 1; }
.cmd-footer kbd {
  font-family: ui-monospace, monospace;
  font-size: 10px;
  padding: 2px 6px;
  margin-right: 4px;
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.16));
  border-radius: 4px;
  background: var(--bg-app, #1f1f23);
}
.cmd-fade-enter-active, .cmd-fade-leave-active { transition: opacity 0.15s; }
.cmd-fade-enter-from, .cmd-fade-leave-to { opacity: 0; }
</style>