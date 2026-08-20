<script setup lang="ts">
import { NCard, NTag, NText, NButton } from 'naive-ui'
import type { Citation } from '@/api/chat'

defineProps<{
  citation: Citation
  index: number
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <n-card size="small" :bordered="false" class="citation-preview">
    <div class="cp-head">
      <n-tag size="small" :bordered="false">[{{ index }}]</n-tag>
      <n-text strong style="font-size: 12px">{{ citation.title || citation.note_id }}</n-text>
      <n-text depth="3" style="font-size: 11px; margin-left: auto">
        chunk #{{ citation.chunk_index }}
        <span v-if="citation.score !== undefined"> · score {{ citation.score.toFixed(3) }}</span>
      </n-text>
      <n-button size="tiny" quaternary circle @click="emit('close')" aria-label="close">
        <template #icon>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </template>
      </n-button>
    </div>
    <n-text depth="2" class="cp-snippet">{{ citation.snippet }}</n-text>
  </n-card>
</template>

<style scoped>
.citation-preview {
  margin-top: 6px;
  max-width: 70%;
  background: var(--hover-bg) !important;
}
.cp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.cp-snippet {
  display: block;
  font-size: 12px;
  line-height: 1.5;
  font-style: italic;
  white-space: pre-wrap;
}
</style>
