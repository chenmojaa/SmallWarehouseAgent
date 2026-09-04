<script setup lang="ts">
const filterSource = ref('')
const filterTag = ref('')
const dateFrom = ref('')
const dateTo = ref('')
function applyFilter() { /* hook into existing search */ }

import { ref, computed, onMounted } from 'vue'
import { t } from '@/i18n'
import { useNotesStore } from '@/stores/notes'
import {
  getFeishuConfig,
  getFeishuStatus,
  listFeishuSpaces,
  syncFeishu,
  type FeishuSpace,
  type FeishuStatus,
  type FeishuSyncResult,
} from '@/api/feishu'
import {
  NCard, NSpace, NText, NTag, NInput, NButton, useMessage,
  NPopconfirm, NEmpty, NSpin, NUpload,
} from 'naive-ui'
import type { UploadCustomRequestOptions } from 'naive-ui'

const notes = useNotesStore()
const message = useMessage()

const tab = ref<'upload' | 'url' | 'text'>('upload')
const listFilter = ref<'all' | 'local' | 'feishu'>('all')
const keyword = ref('')
const urlInput = ref('')
const textInput = ref('')
const textTitle = ref('')
const dragOver = ref(false)

const feishuStatus = ref<FeishuStatus | null>(null)
const feishuSpaces = ref<FeishuSpace[]>([])
const selectedSpaceId = ref<string | null>(null)
const syncing = ref(false)
const refreshingSources = ref(false)
const syncResults = ref<FeishuSyncResult[]>([])
const webUrl = ref('')

onMounted(async () => {
  loadKnowledge()
  loadFeishuData()
})

async function loadKnowledge() {
  await Promise.allSettled([notes.load(), notes.refreshStats()])
}

async function loadFeishuData() {
  refreshingSources.value = true
  try {
    const [config, status] = await Promise.all([getFeishuConfig(), getFeishuStatus()])
    webUrl.value = config.web_url || ''
    feishuStatus.value = status
    if (feishuStatus.value.enabled) {
      const data = await listFeishuSpaces()
      feishuSpaces.value = data.items
    }
  } catch {
    feishuSpaces.value = []
  } finally {
    refreshingSources.value = false
  }
}

function selectSpace(spaceId?: string) {
  selectedSpaceId.value = !spaceId || selectedSpaceId.value === spaceId ? null : spaceId
}

async function runSync() {
  syncing.value = true
  try {
    const response = await syncFeishu(selectedSpaceId.value)
    syncResults.value = response.results || []
    await loadKnowledge()
    const synced = syncResults.value.reduce((sum: number, item: FeishuSyncResult) => sum + item.synced + item.updated, 0)
    if (syncResults.value.some((item: FeishuSyncResult) => item.failed > 0)) {
      message.warning('同步完成，但部分内容失败')
    } else {
      message.success(synced > 0 ? `已同步 ${synced} 条内容` : '内容已是最新')
    }
  } catch (error) {
    message.error((error as Error).message)
  } finally {
    syncing.value = false
  }
}

async function addUrl() {
  if (!urlInput.value.trim()) return
  try {
    const note = await notes.addUrl(urlInput.value.trim())
    message.info(`已添加：${note.title}`)
    urlInput.value = ''
  } catch (error) {
    message.error((error as Error).message)
  }
}

async function addText() {
  if (!textInput.value.trim()) return
  try {
    const note = await notes.addText(textInput.value, textTitle.value || undefined)
    message.info(`已添加：${note.title}`)
    textInput.value = ''
    textTitle.value = ''
  } catch (error) {
    message.error((error as Error).message)
  }
}

async function uploadOne(file: File) {
  try {
    const note = await notes.uploadFile(file)
    if (note) message.info(`已添加：${note.title}`)
  } catch (error) {
    message.error(`${file.name}: ${(error as Error).message}`)
  }
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  dragOver.value = false
  const files = event.dataTransfer?.files
  if (!files) return
  Array.from(files).forEach(uploadOne)
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
  dragOver.value = true
}

function handleDragLeave() {
  dragOver.value = false
}

const uploadHandler = ({ file, onFinish, onError }: UploadCustomRequestOptions) => {
  const selected = file.file as File | null
  if (!selected) {
    onError()
    return
  }
  notes.uploadFile(selected).then(() => onFinish()).catch(() => onError())
}

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.csv,.html,.htm,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff'

function matchKeyword(title: string, summary?: string) {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return true
  const t = decodeUnicode(title)
  const s = decodeUnicode(summary || '')
  return t.toLowerCase().includes(query) || s.toLowerCase().includes(query)
}

function decodeUnicode(s: string): string {
  if (!s) return s
  return s.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
}

const visibleFeishuNotes = computed(() => notes.items
  .filter(note => note.source_type.startsWith('feishu_'))
  .filter(note => matchKeyword(note.title, note.summary)))

const visibleLocalNotes = computed(() => notes.items
  .filter(note => !note.source_type.startsWith('feishu_'))
  .filter(note => matchKeyword(note.title, note.summary)))

const showFeishu = computed(() => listFilter.value !== 'local')
const showLocal = computed(() => listFilter.value !== 'feishu')
const showEmptyState = computed(() =>
  (!showFeishu.value || visibleFeishuNotes.value.length === 0) &&
  (!showLocal.value || visibleLocalNotes.value.length === 0))

const totalNotes = computed(() => notes.stats?.sqlite.total_notes || notes.items.length)
const embeddedNotes = computed(() => notes.stats?.sqlite.embedded_notes || 0)
const embeddedPercent = computed(() => totalNotes.value
  ? Math.round((Math.min(embeddedNotes.value, totalNotes.value) / totalNotes.value) * 100)
  : 0)
const vectorChunks = computed(() => notes.stats?.chroma.count || 0)

const metrics = computed(() => [
  { label: '知识总数', value: totalNotes.value, hint: '已入库的全部来源' },
  { label: '向量检索', value: `${vectorChunks.value}`, hint: '可召回的内容块' },
  { label: '飞书同步', value: visibleFeishuNotes.value.length, hint: '文档与多维表格' },
  { label: '索引覆盖', value: `${embeddedPercent.value}%`, hint: `${embeddedNotes.value} / ${totalNotes.value} 条` },
])

const filters = [
  { key: 'all', label: '全部' },
  { key: 'local', label: '本地内容' },
  { key: 'feishu', label: '飞书' },
] as const

function sourceLabel(type: string) {
  const mapping: Record<string, string> = {
    url: '网页',
    text: '文本',
    image: '图片',
    pdf: 'PDF',
    docx: 'Word',
    pptx: 'PPT',
    xlsx: 'Excel',
    csv: 'CSV',
    html: 'HTML',
    feishu_docx: '飞书文档',
    feishu_bitable: '多维表格',
  }
  return mapping[type] || type.toUpperCase()
}

function sourceTone(type: string) {
  if (type === 'image') return 'warning'
  if (type.startsWith('feishu_docx')) return 'success'
  if (type.startsWith('feishu_bitable')) return 'warning'
  return 'info'
}

function formatDate(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

async function reembed(id: string) {
  try {
    await notes.reembed(id)
    message.success('已完成向量化')
  } catch (error) {
    message.error((error as Error).message)
  }
}

async function removeNote(id: string) {
  try {
    await notes.remove(id)
    message.success('已删除')
  } catch (error) {
    message.error((error as Error).message)
  }
}

function downloadNote(id: string, title: string) {
  const safeName = (title || 'note').replace(/[^a-zA-Z0-9._-]+/g, '_') + '.md'
  const link = document.createElement('a')
  link.href = `/api/notes/${encodeURIComponent(id)}/download`
  link.download = safeName
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function openExternal(url?: string | null) {
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div class="kb-page">
    <header class="page-hero">
      <div>
        <span class="eyebrow">KNOWLEDGE BASE</span>
        <h1>{{ t('nav.notes', '知识库', 'Knowledge Base') }}</h1>
        <p>{{ t('ui.sync.004', '集中管理本地文件、网页、文本，以及飞书文档和多维表格。', '集中管理本地文件、网页、文本，以及飞书文档和多维表格。') }}</p>
      </div>
      <n-button secondary :loading="refreshingSources" @click="loadFeishuData">{{ t('ui.misc.012', '刷新状态', '刷新状态') }}</n-button>
    </header>

    <section class="metrics-grid">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.hint }}</small>
      </article>
    </section>

    <n-card class="panel-card" :bordered="false">
      <template #header>
        <div class="panel-title">
          <strong>{{ t('ui.misc.046', '添加内容', '添加内容') }}</strong>
          <span>{{ t('ui.misc.035', '新内容会自动解析并进入检索索引', '新内容会自动解析并进入检索索引') }}</span>
        </div>
      </template>
      <div class="segment-tabs">
        <button
          v-for="item in [{ key: 'upload', label: '上传文件' }, { key: 'url', label: '网页' }, { key: 'text', label: '文本' }]"
          :key="item.key"
          :class="{ active: tab === item.key }"
          @click="tab = item.key as any"
        >
          {{ item.label }}
        </button>
      </div>

      <div v-if="tab === 'upload'" class="drop-zone" :class="{ active: dragOver }" @drop="handleDrop" @dragover="handleDragOver" @dragleave="handleDragLeave">
        <svg class="drop-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 16V4" />
          <path d="m7 9 5-5 5 5" />
          <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
        </svg>
        <strong>{{ t('ui.misc.031', '拖拽文件到这里', '拖拽文件到这里') }}</strong>
        <p>{{ t('ui.misc.003', 'PDF · DOCX · PPTX · XLSX · CSV · HTML · TXT/MD · 图片 OCR', 'PDF · DOCX · PPTX · XLSX · CSV · HTML · TXT/MD · 图片 OCR') }}</p>
        <n-upload :accept="ACCEPT" :custom-request="uploadHandler" :show-file-list="false" multiple>
          <n-button type="primary" round>{{ t('ui.misc.053', '选择文件', '选择文件') }}</n-button>
        </n-upload>
        <div v-if="notes.uploadProgress" class="progress-note" :class="notes.uploadProgress.status">
          <n-spin v-if="notes.uploadProgress.status === 'uploading'" size="small" />
          <span>{{ notes.uploadProgress.name }} {{ notes.uploadProgress.status === 'uploading' ? '处理中' : notes.uploadProgress.status === 'done' ? '完成' : notes.uploadProgress.status === 'canceled' ? '已取消' : notes.uploadProgress.message }}</span>
          <button v-if="notes.uploadProgress.status === 'uploading'" class="cancel-btn" @click="notes.cancelUpload()">{{ t('chat.perm.confirm.cancel', '取消', 'Cancel') }}</button>
        </div>
      </div>

      <div v-else-if="tab === 'url'" class="inline-form">
        <n-input v-model:value="urlInput" :placeholder="t('ui.notes.004', '粘贴文章链接', '粘贴文章链接')" size="large" @keyup.enter="addUrl" />
        <n-button type="primary" size="large" :loading="notes.ingesting" @click="addUrl">{{ t('ui.notes.002', '抓取入库', '抓取入库') }}</n-button>
      </div>

      <div v-else class="stack-form">
        <n-input v-model:value="textTitle" :placeholder="t('ui.misc.043', '标题（可选）', '标题（可选）')" />
        <n-input v-model:value="textInput" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" :placeholder="t('ui.notes.005', '粘贴需要保存的文本…', '粘贴需要保存的文本…')" />
        <n-button type="primary" :loading="notes.ingesting" @click="addText">{{ t('ui.notes.001', '保存并入库', '保存并入库') }}</n-button>
      </div>
    </n-card>

    <div class="toolbar">
      <div class="segment-tabs compact">
        <button v-for="filter in filters" :key="filter.key" :class="{ active: listFilter === filter.key }" @click="listFilter = filter.key">
          {{ filter.label }}
        </button>
      </div>
      <n-input v-model:value="keyword" :placeholder="t('ui.misc.033', '搜索标题或摘要', '搜索标题或摘要')" clearable size="large" />
    </div>

    <n-card v-if="showFeishu" class="panel-card feishu-panel" :bordered="false">
      <template #header>
        <div class="panel-title">
          <span class="source-badge feishu">{{ t('ui.misc.057', '飞', '飞') }}</span>
          <strong>{{ t('ui.notes.007', '飞书知识库', '飞书知识库') }}</strong>
          <small class="status-line">
            <i :class="['status-dot', { online: !!feishuStatus?.enabled }]"></i>
            {{ feishuStatus?.enabled ? '已连接' : '未启用' }}
          </small>
        </div>
      </template>
      <template #header-extra>
        <n-space align="center" :size="8">
          <n-text depth="3" style="font-size: 12px">{{ feishuSpaces.length }} 个空间</n-text>
          <n-button size="small" :disabled="!feishuStatus?.enabled" :loading="syncing" @click="runSync">
            {{ selectedSpaceId ? '同步所选' : '全部同步' }}
          </n-button>
        </n-space>
      </template>

      <div v-if="!feishuStatus?.enabled" class="empty-surface">
        <n-empty :description="t('ui.sync.001', '当前尚未启用飞书同步', '当前尚未启用飞书同步')" />
      </div>
      <template v-else>
        <div v-if="feishuSpaces.length" class="space-flow">
          <button class="space-chip" :class="{ selected: selectedSpaceId === null }" @click="selectSpace()">{{ t('ui.misc.011', '全部空间', '全部空间') }}</button>
          <button
            v-for="space in feishuSpaces"
            :key="space.space_id"
            class="space-chip"
            :class="{ selected: selectedSpaceId === space.space_id }"
            @click="selectSpace(space.space_id)"
          >
            {{ space.name || space.space_id }}
          </button>
        </div>

        <div v-if="syncResults.length" class="sync-results">
          <div v-for="result in syncResults" :key="result.space_id" class="sync-row">
            <span>{{ result.space_name || result.space_id }}</span>
            <n-space :size="6">
              <n-tag v-if="result.synced" size="small" round type="success">新增 {{ result.synced }}</n-tag>
              <n-tag v-if="result.updated" size="small" round type="info">更新 {{ result.updated }}</n-tag>
              <n-tag v-if="result.skipped" size="small" round>跳过 {{ result.skipped }}</n-tag>
              <n-tag v-if="result.failed" size="small" round type="error">失败 {{ result.failed }}</n-tag>
            </n-space>
          </div>
        </div>

        <div v-if="notes.loading && visibleFeishuNotes.length === 0" class="loading-row">
          <n-spin size="small" /><span>{{ t('ui.sync.003', '正在加载飞书内容…', '正在加载飞书内容…') }}</span>
        </div>
        <n-empty v-else-if="visibleFeishuNotes.length === 0" :description="t('ui.sync.002', '暂无同步后的飞书内容', '暂无同步后的飞书内容')" />
        <div v-else class="note-list">
          <article v-for="note in visibleFeishuNotes" :key="note.id" class="note-item">
            <div class="note-main">
              <div class="note-title-row">
                <strong>{{ decodeUnicode(note.title) }}</strong>
                <n-tag size="small" round :type="sourceTone(note.source_type) as any">{{ sourceLabel(note.source_type) }}</n-tag>
                <n-tag v-if="note.embedded" size="small" round :bordered="false">{{ note.chunk_count }} 块</n-tag>
                <n-tag v-else size="small" round type="warning">{{ t('ui.misc.024', '待索引', '待索引') }}</n-tag>
              </div>
              <p v-if="note.summary">{{ decodeUnicode(note.summary) }}</p>
            </div>
            <div class="note-actions">
              <span>{{ formatDate(note.created_at) }}</span>
              <a v-if="note.view_url" :href="note.view_url" target="_blank" rel="noreferrer">{{ t('ui.misc.042', '查看', '查看') }}</a>
              <button @click="downloadNote(note.id, note.title)">{{ t('ui.misc.005', '下载', '下载') }}</button>
              <button v-if="!note.embedded" class="warn" @click="reembed(note.id)">{{ t('ui.misc.054', '重建索引', '重建索引') }}</button>
              <n-popconfirm @positive-click="removeNote(note.id)">
                <template #trigger><button class="danger">{{ t('chat.msg.delete', '删除', 'Delete') }}</button></template>
                删除该笔记？
              </n-popconfirm>
            </div>
          </article>
        </div>
      </template>
    </n-card>

    <n-card v-if="showLocal" class="panel-card" :bordered="false">
      <template #header>
        <div class="panel-title">
          <span class="source-badge local">{{ t('ui.misc.037', '本地', '本地') }}</span>
          <strong>{{ t('ui.misc.038', '本地内容', '本地内容') }}</strong>
          <small>{{ visibleLocalNotes.length }} 条</small>
        </div>
      </template>

      <div v-if="notes.loading && visibleLocalNotes.length === 0" class="loading-row">
        <n-spin size="small" /><span>{{ t('ui.misc.044', '正在加载…', '正在加载…') }}</span>
      </div>
      <n-empty v-else-if="visibleLocalNotes.length === 0" :description="t('ui.notes.006', '还没有本地知识内容', '还没有本地知识内容')" />
      <div v-else class="note-list">
        <article v-for="note in visibleLocalNotes" :key="note.id" class="note-item">
            <div class="note-main">
              <div class="note-title-row">
                <strong>{{ decodeUnicode(note.title) }}</strong>
                <n-tag size="small" round :type="sourceTone(note.source_type) as any">{{ sourceLabel(note.source_type) }}</n-tag>
                <n-tag v-if="note.embedded" size="small" round :bordered="false">{{ note.chunk_count }} 块</n-tag>
                <n-tag v-else size="small" round type="warning">{{ t('ui.misc.024', '待索引', '待索引') }}</n-tag>
              </div>
              <p v-if="note.summary">{{ decodeUnicode(note.summary) }}</p>
            </div>
          <div class="note-actions">
            <span>{{ formatDate(note.created_at) }}</span>
            <button v-if="note.source_type === 'url'" @click="openExternal(note.source_url)">{{ t('notes.open', '打开', 'Open') }}</button>
            <button @click="downloadNote(note.id, note.title)">{{ t('ui.misc.005', '下载', '下载') }}</button>
            <button v-if="!note.embedded" class="warn" @click="reembed(note.id)">{{ t('ui.misc.054', '重建索引', '重建索引') }}</button>
            <n-popconfirm @positive-click="removeNote(note.id)">
              <template #trigger><button class="danger">{{ t('chat.msg.delete', '删除', 'Delete') }}</button></template>
              删除该笔记？
            </n-popconfirm>
          </div>
        </article>
      </div>
    </n-card>

    <div v-if="notes.loading && showEmptyState && notes.items.length === 0" class="global-loading">
      <n-spin size="large" />
    </div>
  </div>
</template>

<style scoped>
.kb-page {
  min-height: 100%;
  max-width: 1160px;
  margin: 0 auto;
  padding: 22px 20px 30px;
  overflow-y: auto;
}

.page-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.eyebrow {
  color: #60a5fa;
  font-size: 11px;
  letter-spacing: 0.18em;
  font-weight: 700;
}

.page-hero h1 {
  margin: 2px 0 6px;
  font-size: 28px;
  line-height: 1.2;
  letter-spacing: -0.04em;
}

.page-hero p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.metric-card,
.panel-card {
  background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
  border: 1px solid var(--border-soft);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}

.metric-card {
  padding: 16px 18px;
  border-radius: 16px;
  position: relative;
  overflow: hidden;
  transition: transform .2s ease, box-shadow .2s ease;
}

.metric-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: linear-gradient(to bottom, #3b82f6, #8b5cf6);
  opacity: .7;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.09);
}

.metric-card span,
.metric-card small {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.metric-card strong {
  display: block;
  margin: 7px 0;
  font-size: 26px;
  line-height: 1;
  letter-spacing: -0.03em;
  background: linear-gradient(135deg, var(--text-primary), color-mix(in srgb, var(--text-primary) 55%, #3b82f6));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.panel-card {
  border-radius: 16px;
  overflow: hidden;
}

.panel-card :deep(.n-card__content) {
  padding-top: 14px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.panel-title span,
.panel-title small {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.source-badge {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.source-badge.feishu { background: linear-gradient(135deg, #3370ff, #17b8a6); }
.source-badge.local { background: linear-gradient(135deg, #3b82f6, #8b5cf6); }
.status-line { display: inline-flex; align-items: center; gap: 6px; }

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;
}

.status-dot.online {
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.14);
}

.segment-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 11px;
  background: var(--hover-bg);
  margin-bottom: 14px;
}

.segment-tabs.compact { margin-bottom: 0; }

.segment-tabs button {
  height: 31px;
  border: 0;
  border-radius: 8px;
  padding: 0 14px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all .2s ease;
}

.segment-tabs button.active {
  color: var(--text-primary);
  background: var(--bg-elevated);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
  font-weight: 600;
}

.drop-zone {
  min-height: 104px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 12px 18px;
  border-radius: 14px;
  border: 1.5px dashed color-mix(in srgb, #3b82f6 38%, transparent);
  background: rgba(59, 130, 246, 0.06);
  transition: all .2s ease;
}

.drop-zone.active {
  border-color: #3b82f6;
  transform: scale(1.005);
  background: rgba(59, 130, 246, 0.11);
}

.drop-zone > strong {
  font-size: 13.5px;
  letter-spacing: -0.01em;
}

.drop-zone p { margin: 0; color: var(--text-muted); font-size: 12px; text-align: center; }

/* n-upload 的触发器默认 inline-block，不居中；强制居中对齐 */
.drop-zone :deep(.n-upload),
.drop-zone :deep(.n-upload-trigger) {
  display: flex;
  justify-content: center;
}

.drop-icon {
  width: 26px;
  height: 26px;
  color: #3b82f6;
  opacity: 0.85;
}

.drop-zone.active .drop-icon {
  transform: translateY(-3px);
  transition: transform .2s ease;
}

.progress-note {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 480px;
  overflow: hidden;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--hover-bg);
  color: var(--text-secondary);
  font-size: 12px;
}

.progress-note.failed span { color: #ef4444; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }

.progress-note.canceled span { color: var(--text-muted); }

.cancel-btn {
  border: 0;
  background: transparent;
  padding: 2px 8px;
  border-radius: 999px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  transition: all .2s ease;
}

.cancel-btn:hover {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.inline-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.stack-form {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.toolbar {
  position: sticky;
  top: 0;
  z-index: 3;
  display: grid;
  grid-template-columns: auto minmax(220px, 380px);
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  background: linear-gradient(to bottom, var(--bg-app) 72%, transparent);
}
.toolbar :deep(.n-input) {
  border-radius: 12px;
}
.toolbar :deep(.n-input .n-input__border),
.toolbar :deep(.n-input .n-input__state-border) {
  border-radius: 12px;
}

.space-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.space-chip {
  height: 32px;
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  padding: 0 13px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: all .2s ease;
}

.space-chip.selected {
  border-color: rgba(59, 130, 246, 0.55);
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
  font-weight: 600;
}

.sync-results {
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 11px;
  background: rgba(59, 130, 246, 0.07);
}

.sync-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}

.note-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.note-item {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 68px;
  padding: 13px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: color-mix(in srgb, var(--bg-app) 40%, transparent);
  transition: border-color .2s ease, background .2s ease, transform .2s ease;
}

.note-item:hover {
  border-color: rgba(59, 130, 246, 0.35);
  background: color-mix(in srgb, #3b82f6 5%, var(--bg-app));
  transform: translateX(2px);
}

.note-main {
  min-width: 0;
  flex: 1;
}

.note-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.note-title-row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}

.note-main p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  margin: 5px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
}

.note-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  gap: 7px;
  color: var(--text-muted);
  font-size: 12px;
}

.note-actions > span {
  margin-right: 4px;
  white-space: nowrap;
}

.note-actions a,
.note-actions button {
  border: 1px solid var(--border-soft);
  background: transparent;
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  transition: all .2s ease;
}

.note-actions a:hover,
.note-actions button:hover {
  border-color: rgba(59, 130, 246, 0.5);
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}
.note-actions button.warn:hover {
  border-color: rgba(245, 158, 11, 0.5);
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}
.note-actions button.danger:hover {
  border-color: rgba(239, 68, 68, 0.5);
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.loading-row,
.empty-surface,
.global-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 36px 0;
  color: var(--text-muted);
  font-size: 13px;
}

.global-loading { min-height: 180px; }

@media (max-width: 900px) {
  .kb-page { padding: 18px 14px 24px; }
  .page-hero { align-items: flex-start; flex-direction: column; }
  .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .inline-form { grid-template-columns: 1fr; }
  .toolbar { grid-template-columns: 1fr; }
  .note-actions span { display: none; }
}

@media (max-width: 520px) {
  .metrics-grid { grid-template-columns: 1fr; }
  .note-item { align-items: stretch; flex-direction: column; gap: 8px; }
  .note-actions { justify-content: flex-start; }
}

.search-filters { display: flex; gap: 6px; align-items: center; padding: 8px 0; flex-wrap: wrap; }
.filter-chip { background: var(--bg-soft); border: 1px solid var(--border-soft); color: var(--text-primary); padding: 4px 10px; border-radius: 6px; font-size: 12px; }
.filter-apply { padding: 4px 12px; border: 0; background: var(--accent, #3b82f6); color: #fff; border-radius: 6px; cursor: pointer; font-size: 12px; }
</style>
