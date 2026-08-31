<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionsStore } from '@/stores/sessions'
import { useChatStore } from '@/stores/chat'
import { useModelsStore } from '@/stores/models'
import {
  downloadSkill,
  getSkillDetail,
  installRecommendedSkill,
  listInstalledSkills,
  listRecommendedSkills,
  removeInstalledSkill,
  uploadSkillFiles,
  type InstalledSkill,
  type RecommendedSkill,
  type SkillDetail,
} from '@/api/skills'
import { NButton, NPopconfirm, NEmpty, NSpin, NText, NModal, NCard, NSpace, NInput, NTag } from 'naive-ui'

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

function gotoMcp() {
  router.push({ name: 'mcp' })
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

// === Skill dialog ===
const skillOpen = ref(false)
const skillTab = ref<'recommended' | 'mine'>('recommended')
const recommended = ref<RecommendedSkill[]>([])
const installedSkills = ref<InstalledSkill[]>([])
const skillsLoading = ref(false)
const skillError = ref('')
const uploading = ref(false)
const installingId = ref('')
const uploadProgress = ref('')
const dragActive = ref(false)
const uploadOpen = ref(false)
const pickInput = ref<HTMLInputElement | null>(null)

async function loadSkillData() {
  skillsLoading.value = true
  skillError.value = ''
  try {
    const [recommendedResult, installedResult] = await Promise.all([
      listRecommendedSkills(),
      listInstalledSkills(),
    ])
    recommended.value = recommendedResult.items
    installedSkills.value = installedResult.items
  } catch (error) {
    skillError.value = (error as Error).message
  } finally {
    skillsLoading.value = false
  }
}

function openSkill() {
  skillOpen.value = true
  skillTab.value = 'recommended'
  if (!recommended.value.length || !installedSkills.value.length) void loadSkillData()
}

async function install(skill: RecommendedSkill) {
  installingId.value = skill.id
  try {
    await installRecommendedSkill(skill.id)
    await loadSkillData()
  } catch (error) {
    skillError.value = `${skill.name}: ${(error as Error).message}`
  } finally {
    installingId.value = ''
  }
}

function uploadPickedFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  void submitUpload(selected)
  input.value = ''
}

async function submitUpload(files: File[], sourceName?: string) {
  if (!files.length) return
  uploading.value = true
  skillError.value = ''
  uploadProgress.value = '正在解析技能包…'
  const relativeFile = files[0] as File & { webkitRelativePath?: string }
  const derivedSource = sourceName ||
    relativeFile.webkitRelativePath?.split('/')[0] ||
    files[0].name.replace(/\.(zip|tar|tgz|tar\.gz)$/i, '')
  try {
    const result = await uploadSkillFiles(files, derivedSource)
    await loadSkillData()
    skillTab.value = 'mine'
    uploadOpen.value = false
    uploadProgress.value = `已导入 ${result.items.length} 个技能`
    setTimeout(() => { uploadProgress.value = '' }, 2600)
  } catch (error) {
    skillError.value = (error as Error).message.replace(/^\d+\s*/, '')
    uploadProgress.value = ''
  } finally {
    uploading.value = false
  }
}

async function filesFromDataTransfer(dt: DataTransfer): Promise<File[]> {
  // 优先用目录条目递归读取（支持拖入文件夹），否则退回普通文件列表
  const entries = Array.from(dt.items || [])
    .map(item => item.webkitGetAsEntry?.())
    .filter(Boolean) as FileSystemEntry[]
  if (!entries.length) return Array.from(dt.files || [])
  const files: File[] = []
  const walk = async (entry: FileSystemEntry, path: string) => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject))
      files.push(Object.defineProperty(file, 'webkitRelativePath', { value: path + file.name }) as File)
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      let batch: FileSystemEntry[]
      do {
        batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve as never, reject))
        for (const child of batch) await walk(child, path + entry.name + '/')
      } while (batch.length)
    }
  }
  for (const entry of entries) await walk(entry, '')
  return files
}

async function onDrop(event: DragEvent) {
  event.preventDefault()
  dragActive.value = false
  const dt = event.dataTransfer
  if (!dt) return
  const files = await filesFromDataTransfer(dt)
  void submitUpload(files)
}

async function removeSkill(id: string) {
  try {
    await removeInstalledSkill(id)
    expandedSkillId.value = ''
    await loadSkillData()
  } catch (error) {
    skillError.value = (error as Error).message
  }
}

// === 我的技能：展开/收起 + 详情（文件结构 / 下载） ===
const expandedSkillId = ref('')
const detailLoading = ref('')
const skillDetails = ref<Record<string, SkillDetail>>({})

// === 技能搜索：推荐 / 我的技能共用 ===
const skillSearch = ref('')
const filteredRecommended = computed(() => {
  const q = skillSearch.value.trim().toLowerCase()
  if (!q) return recommended.value
  return recommended.value.filter(s =>
    s.name.toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q) ||
    (s.badge || '').toLowerCase().includes(q) ||
    s.category.toLowerCase().includes(q)
  )
})
const filteredInstalled = computed(() => {
  const q = skillSearch.value.trim().toLowerCase()
  if (!q) return installedSkills.value
  return installedSkills.value.filter(s =>
    s.name.toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q) ||
    (s.source_label || '').toLowerCase().includes(q)
  )
})

async function toggleSkillDetail(skill: InstalledSkill) {
  if (expandedSkillId.value === skill.id) {
    expandedSkillId.value = ''
    return
  }
  expandedSkillId.value = skill.id
  if (!skillDetails.value[skill.id]) {
    detailLoading.value = skill.id
    try {
      skillDetails.value[skill.id] = await getSkillDetail(skill.id)
    } catch (error) {
      skillError.value = (error as Error).message
      expandedSkillId.value = ''
    } finally {
      detailLoading.value = ''
    }
  }
}

async function handleDownload(id: string) {
  try {
    await downloadSkill(id)
  } catch (error) {
    skillError.value = (error as Error).message
  }
}

const categoryLabels: Record<string, string> = {
  documents: '文档',
  data: '数据',
  engineering: '研发',
  design: '设计',
  agent: 'Agent',
  custom: '自定义',
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function sourceLabel(skill: InstalledSkill) {
  if (skill.source_type === 'github') return 'GitHub'
  if (skill.source_type === 'folder') return '文件夹'
  if (skill.source_type === 'archive') return '压缩包'
  return '本地上传'
}
</script>

<template>
  <div class="chat-history">
    <div class="chat-history-actions">
      <n-button block quaternary @click="newChat" class="action-btn new-chat-btn">+ 新对话</n-button>
      <n-button block quaternary @click="gotoNotes" class="action-btn">知识库</n-button>
      <n-button block quaternary @click="openSearch" class="action-btn">搜索对话</n-button>
      <n-button block quaternary @click="openSkill" class="action-btn">技能</n-button>
      <n-button block quaternary @click='gotoMcp' class='action-btn'>MCP</n-button>
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

  <!-- Skill 弹窗 -->
  <n-modal v-model:show="skillOpen" preset="card" title="技能中心" style="width: 880px; max-width: calc(100vw - 32px)">
    <div class="skill-center">
      <div class="skill-topbar">
        <div class="skill-tabs">
          <button :class="{ active: skillTab === 'recommended' }" @click="skillTab = 'recommended'">推荐首页</button>
          <button :class="{ active: skillTab === 'mine' }" @click="skillTab = 'mine'">我的技能</button>
        </div>
        <n-button size="small" round type="primary" :disabled="uploading" @click="uploadOpen = true">
          添加技能
        </n-button>
      </div>

      <n-input
        v-model:value="skillSearch"
        class="skill-search"
        size="small"
        round
        clearable
        :placeholder="skillTab === 'recommended' ? '搜索推荐技能' : '搜索我的技能'"
      >
        <template #prefix><span class="skill-search-icon">🔍</span></template>
      </n-input>

      <div class="skill-scroll">
        <div v-if="skillsLoading" class="skill-state"><n-spin size="small" /><span>正在加载技能…</span></div>
        <div v-else-if="skillError" class="skill-alert">{{ skillError }}</div>
        <div v-if="uploadProgress" class="skill-success">{{ uploadProgress }}</div>

        <template v-if="skillTab === 'recommended' && !skillsLoading">
        <div class="skill-note">
          <strong>来自 GitHub 的实用技能</strong>
          <span>官方仓库 · anthropics/skills · 导入后保留完整包文件</span>
        </div>

        <n-empty v-if="filteredRecommended.length === 0" class="empty-spacing" description="没有匹配的推荐技能" />
        <div v-else class="skill-grid wide">
          <article v-for="skill in filteredRecommended" :key="skill.id" class="skill-card">
            <div class="skill-card-top">
              <span class="skill-icon">{{ skill.emoji }}</span>
              <n-tag size="tiny" round :bordered="false" type="info">{{ skill.badge || categoryLabels[skill.category] || skill.category }}</n-tag>
            </div>
            <h3>{{ skill.name }}</h3>
            <p>{{ skill.description }}</p>
            <div class="skill-footer">
              <a :href="skill.source_url" target="_blank" rel="noreferrer">GitHub ↗</a>
              <n-button
                size="tiny"
                round
                :type="skill.installed ? 'default' : 'primary'"
                :loading="installingId === skill.id"
                :disabled="skill.installed"
                @click="install(skill)"
              >
                {{ skill.installed ? '已安装' : '安装' }}
              </n-button>
            </div>
          </article>
        </div>
      </template>

      <template v-else-if="!skillsLoading">
        <n-empty v-if="filteredInstalled.length === 0" class="empty-spacing" :description="skillSearch ? '没有匹配的技能' : '还没有本地技能，点击右上角「添加技能」上传导入'" />
        <div v-else class="owned-list">
          <article v-for="skill in filteredInstalled" :key="skill.id" class="owned-item owned-item-wrap">
            <div class="owned-row">
              <div class="owned-main">
                <div class="owned-title">
                  <strong>{{ skill.name }}</strong>
                  <n-tag size="tiny" round :bordered="false">{{ sourceLabel(skill) }}</n-tag>
                </div>
                <p v-if="skill.description" class="owned-desc" :class="{ clamped: expandedSkillId !== skill.id }">{{ skill.description }}</p>
                <small>{{ skill.file_count }} 个文件 · {{ formatSize(skill.size_bytes) }} · {{ formatDate(skill.installed_at) }}</small>
              </div>
              <div class="owned-actions">
                <button type="button" class="expand-toggle" @click="toggleSkillDetail(skill)">
                  {{ expandedSkillId === skill.id ? '收起 ▴' : '展开 ▾' }}
                </button>
                <a v-if="skill.source_url" :href="skill.source_url" target="_blank" rel="noreferrer">来源</a>
                <n-popconfirm @positive-click="removeSkill(skill.id)">
                  <template #trigger><button type="button">删除</button></template>
                  删除该技能？
                </n-popconfirm>
              </div>
            </div>
            <div v-if="expandedSkillId === skill.id" class="owned-detail">
              <n-spin v-if="detailLoading === skill.id" size="small" class="detail-spin" />
              <template v-else-if="skillDetails[skill.id]">
                <div class="detail-section">
                  <div class="detail-head">
                    <strong>文件结构</strong>
                    <n-button size="tiny" round type="primary" @click="handleDownload(skill.id)">下载 zip</n-button>
                  </div>
                  <ul class="file-tree">
                    <li v-for="file in skillDetails[skill.id].files" :key="file">
                      <span class="file-icon">📄</span>{{ file }}
                    </li>
                  </ul>
                </div>
                <details class="detail-section">
                  <summary>SKILL.md 内容</summary>
                  <pre class="skill-md">{{ skillDetails[skill.id].content }}</pre>
                </details>
              </template>
            </div>
          </article>
        </div>
      </template>
      </div>
    </div>
  </n-modal>

  <!-- 添加技能弹窗：单一选择入口 -->
  <n-modal v-model:show="uploadOpen" preset="card" title="添加技能" style="max-width: 460px">
    <div class="skill-upload-body">
      <p class="skill-upload-tip">请选择包含 <code>SKILL.md</code> 的技能文件夹或压缩包（.zip / .tar.gz / .tgz）</p>
      <div
        class="skill-dropzone"
        :class="{ active: dragActive, disabled: uploading }"
        @click="!uploading && pickInput?.click()"
        @drop="onDrop"
        @dragover.prevent="dragActive = true"
        @dragleave="dragActive = false"
      >
        <span class="dropzone-icon">📂</span>
        <strong>{{ uploading ? '正在上传并解压…' : '点击选择文件夹或压缩包' }}</strong>
        <p>也可以将技能文件夹直接拖拽到这里</p>
      </div>
      <input ref="pickInput" class="hidden-input" type="file" multiple @change="uploadPickedFiles">
    </div>
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
}
.action-btn {
  height: 36px;
  border: none !important;
  background: transparent !important;
}
.action-btn:hover {
  background: var(--hover-bg) !important;
}
.new-chat-btn {
  font-weight: 600;
}
.new-chat-btn:hover {
  background: var(--active-bg) !important;
}
.action-btn + .action-btn {
  margin-top: 8px;
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
.skill-center { height: 520px; display: flex; flex-direction: column; overflow: hidden; }
.skill-scroll { flex: 1; min-height: 0; overflow-y: auto; padding-right: 4px; }
.skill-search { margin-bottom: 12px; flex-shrink: 0; }
.skill-search-icon { opacity: 0.55; font-size: 12px; }
.skill-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.skill-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: var(--hover-bg);
}
.skill-tabs button {
  height: 30px;
  min-width: 88px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.skill-tabs button.active {
  color: var(--text-primary);
  font-weight: 600;
  background: var(--bg-elevated);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
}
.skill-note {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}
.skill-note strong { font-size: 14px; }
.skill-note span { color: var(--text-muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-upload-body { display: grid; gap: 12px; }
.skill-upload-tip {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}
.skill-upload-tip code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--hover-bg);
  font-size: 11px;
}
.skill-dropzone {
  display: grid;
  justify-items: center;
  gap: 6px;
  padding: 30px 18px;
  border: 1.5px dashed rgba(59, 130, 246, .35);
  border-radius: 13px;
  background: rgba(59, 130, 246, .06);
  cursor: pointer;
  text-align: center;
  transition: all .2s ease;
}
.skill-dropzone:hover,
.skill-dropzone.active {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, .11);
}
.skill-dropzone.disabled { opacity: .5; pointer-events: none; }
.dropzone-icon { font-size: 28px; }
.skill-dropzone strong { font-size: 14px; }
.skill-dropzone p { margin: 0; color: var(--text-muted); font-size: 12px; }
.hidden-input { display: none; }
.skill-state,
.skill-success,
.skill-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 9px;
  font-size: 12px;
}
.skill-state { justify-content: center; background: var(--hover-bg); color: var(--text-muted); }
.skill-success { justify-content: center; background: rgba(34, 197, 94, .1); color: #16a34a; }
.skill-alert { background: rgba(239, 68, 68, .08); color: #dc2626; word-break: break-word; }
.skill-grid.wide { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.skill-card {
  padding: 15px;
  border: 1px solid var(--border-soft);
  border-radius: 15px;
  background: var(--bg-elevated);
  box-shadow: 0 6px 18px rgba(15, 23, 42, .05);
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}
.skill-card:hover {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, .4);
  box-shadow: 0 10px 24px rgba(15, 23, 42, .09);
}
.skill-card-top { display: flex; align-items: center; justify-content: space-between; }
.skill-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: rgba(59, 130, 246, .1);
  font-size: 20px;
}
.skill-card h3 { margin: 13px 0 5px; font-size: 15px; line-height: 1.25; }
.skill-card p {
  min-height: 54px;
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}
.skill-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
.skill-footer a { color: var(--text-muted); font-size: 12px; text-decoration: none; }
.skill-footer a:hover { color: #3b82f6; }
.owned-list { border-top: 1px solid var(--border-soft); }
.owned-item-wrap { padding: 13px 2px; border-bottom: 1px solid var(--border-soft); }
.owned-item-wrap:last-child { border-bottom: 0; }
.owned-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.owned-main { min-width: 0; }
.owned-title { display: flex; align-items: center; gap: 8px; }
.owned-title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.owned-desc {
  margin: 4px 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-line;
}
/* 默认收起：最多显示两行，超出省略 */
.owned-desc.clamped {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.expand-toggle {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}
.expand-toggle:hover { color: #3b82f6; }
.owned-detail {
  margin-top: 10px;
  padding: 12px;
  border-radius: 10px;
  background: var(--hover-bg);
  display: grid;
  gap: 10px;
}
.detail-spin { justify-self: center; padding: 16px 0; }
.detail-section { display: grid; gap: 8px; }
.detail-head { display: flex; align-items: center; justify-content: space-between; }
.detail-head strong { font-size: 12px; color: var(--text-primary); }
.file-tree {
  margin: 0;
  padding: 0 0 0 4px;
  list-style: none;
  max-height: 180px;
  overflow-y: auto;
  display: grid;
  gap: 3px;
}
.file-tree li {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-icon { flex-shrink: 0; font-size: 11px; }
.detail-section summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  user-select: none;
}
.detail-section summary:hover { color: #3b82f6; }
.skill-md {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: var(--bg-app, rgba(0, 0, 0, .04));
  max-height: 260px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.owned-main small { color: var(--text-muted); font-size: 11px; }
.owned-actions { flex-shrink: 0; display: flex; align-items: center; gap: 10px; }
.owned-actions a { color: var(--text-secondary); font-size: 12px; text-decoration: none; }
.owned-actions a:hover { color: #3b82f6; }
.owned-actions button { border: 0; padding: 0; background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; }
.owned-actions button:hover { color: #ef4444; }
.empty-spacing { margin-top: 52px; }
@media (max-width: 820px) {
  .skill-grid.wide { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .skill-topbar { align-items: stretch; flex-direction: column; }
  .skill-grid.wide { grid-template-columns: 1fr; }
  .owned-item { align-items: stretch; flex-direction: column; gap: 8px; }
}
</style>
