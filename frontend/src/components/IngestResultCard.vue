<script setup lang="ts">
import { computed } from 'vue'
import type { IngestResult } from '@/api/chat'
import { NTag } from 'naive-ui'

const props = defineProps<{
  data: IngestResult
}>()

const status = computed<{ tone: 'success' | 'warn' | 'error'; text: string }>(() => {
  if (!props.data.ok) return { tone: 'error', text: '\u5165\u5e93\u5931\u8d25' }
  if (props.data.duplicate_of) return { tone: 'warn', text: '\u5df2\u5165\u5e93\uff08\u7591\u4f3c\u91cd\u590d\uff09' }
  if (props.data.embedded) return { tone: 'success', text: '\u5165\u5e93\u5e76\u5df2 embedding' }
  return { tone: 'warn', text: '\u5165\u5e93\uff08\u672a embedding\uff09' }
})

const sourceTypeLabel = computed<string>(() => {
  const st = props.data.source_type || ''
  if (st === 'feishu_docx') return '\u98de\u4e66\u6587\u6863'
  if (st === 'feishu_bitable') return '\u98de\u4e66\u591a\u7ef4\u8868\u683c'
  if (st === 'url') return 'URL \u6293\u53d6'
  if (st === 'text') return '\u6587\u672c'
  if (st === 'pdf' || st === 'docx' || st === 'pptx' || st === 'xlsx' || st === 'csv' || st === 'html') return st.toUpperCase()
  if (st === 'image') return '\u56fe\u7247'
  return st || '-'
})
</script>

<template>
  <div class="ingest-card" :data-tone="status.tone">
    <div class="ingest-head">
      <div class="ingest-title">{{ data.title || '\uff08\u65e0\u6807\u9898\uff09' }}</div>
      <NTag size="small" :type="status.tone === 'success' ? 'success' : status.tone === 'warn' ? 'warning' : 'error'">
        {{ status.text }}
      </NTag>
    </div>

    <div v-if="data.summary" class="ingest-summary">{{ data.summary }}</div>

    <div class="ingest-meta">
      <span class="meta-item">\u6765\u6e90\uff1a{{ sourceTypeLabel }}</span>
      <span v-if="data.chunk_count !== undefined" class="meta-item">chunks\uff1a{{ data.chunk_count }}</span>
      <span v-if="data.note_id" class="meta-item">id\uff1a{{ data.note_id.slice(0, 8) }}</span>
    </div>

    <div v-if="data.tags && data.tags.length" class="ingest-tags">
      <NTag v-for="t in data.tags" :key="t" size="small" :bordered="false">{{ t }}</NTag>
    </div>

    <div v-if="data.duplicate_of" class="ingest-dup">
      \u26a0\ufe0f \u4e0e\u5df2\u6709\u7b14\u8bb0\u91cd\u590d\uff1a#{{ data.duplicate_of }}
    </div>

    <div v-if="!data.ok && data.error" class="ingest-error">\u9519\u8bef\uff1a{{ data.error }}</div>
  </div>
</template>

<style scoped>
.ingest-card {
  background: var(--bg-card, #1f1f23);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  border-left: 3px solid var(--accent, #3b82f6);
  border-radius: 8px;
  padding: 12px 14px;
  margin: 8px 0;
  font-size: 13px;
  max-width: 560px;
}
.ingest-card[data-tone="warn"]  { border-left-color: #f59e0b; }
.ingest-card[data-tone="error"] { border-left-color: #ef4444; }
.ingest-card[data-tone="success"] { border-left-color: #10b981; }

.ingest-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
.ingest-title {
  font-weight: 600;
  font-size: 14px;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ingest-summary {
  color: var(--text-secondary, #aaa);
  margin-bottom: 8px;
  line-height: 1.5;
}
.ingest-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--text-tertiary, #888);
  font-size: 12px;
  margin-bottom: 6px;
}
.meta-item { font-family: monospace; }
.ingest-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.ingest-dup {
  margin-top: 6px;
  font-size: 12px;
  color: #f59e0b;
}
.ingest-error {
  margin-top: 6px;
  font-size: 12px;
  color: #ef4444;
}
</style>