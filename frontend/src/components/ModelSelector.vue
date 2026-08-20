<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useModelsStore, type ReasoningLevel } from '@/stores/models'
import { NSelect, NButton } from 'naive-ui'

const models = useModelsStore()
const router = useRouter()

const DEBUG = import.meta.env.DEV
function dbg(...args) { if (DEBUG) console.debug("[ModelSelector]", ...args) }

const REASONING_OPTIONS = [
  { label: '低', value: 'low' as ReasoningLevel },
  { label: '中', value: 'medium' as ReasoningLevel },
  { label: '高', value: 'high' as ReasoningLevel },
  { label: '极高', value: 'xhigh' as ReasoningLevel },
]

const modelOptions = computed(() => {
  const out: { label: string; value: string }[] = []
  for (const m of models.list) {
    for (const mm of m.models) {
      out.push({ label: mm.name, value: `k|${m.id}|${mm.name}` })
    }
  }
  return out
})

const hasAny = computed(() => models.list.length > 0)

const currentModel = computed(() => {
  const sel = models.selected
  if (!sel) return null
  return `k|${sel.id}|${sel.modelName}`
})

// Sanity: if the persisted selectedId is dangling, fall back to the first
// entry. Watching selectedId + list lets us recover as soon as the user adds a
// new entry, before they pick anything from the dropdown.
watch(
  () => [models.selectedId, models.list.length] as const,
  ([id, n]) => {
    if (n === 0) return
    if (id && !models.list.some(x => x.id === id)) {
      dbg("dangling selectedId, recovering", { id, first: models.list[0]?.id })
      models.select(models.list[0].id)
    }
  },
  { immediate: true },
)

const currentReasoning = computed(() => models.selected?.reasoning ?? 'medium')

function onModelChange(v: string) {
  if (!v.startsWith("k|")) return
  const parts = v.slice(2).split("|")
  const [id, ...rest] = parts
  const modelName = rest.join("|")
  dbg("onModelChange picked", { id, modelName, beforeSelectedId: models.selectedId, beforeDefaultModel: models.list.find(x => x.id === id)?.defaultModel })
  if (models.selectedId !== id) models.select(id)
  const entry = models.list.find(x => x.id === id)
  if (entry && entry.defaultModel !== modelName) {
    models.update(id, { defaultModel: modelName })
  }
  dbg("onModelChange after", { selectedId: models.selectedId, defaultModel: models.list.find(x => x.id === id)?.defaultModel })
}

function onReasoningChange(v: ReasoningLevel) {
  const sel = models.selected
  if (!sel) return
  dbg("onReasoningChange", { from: sel.reasoning, to: v, selId: sel.id, selModelName: sel.modelName, modelsBefore: JSON.parse(JSON.stringify(sel.models)) })
  const newModels = sel.models.map(m => m.name === sel.modelName ? { ...m, reasoning: v } : m)
  models.update(sel.id, { models: newModels })
}

function gotoSettings() {
  router.push({ name: "settings" })
}
</script>

<template>
  <n-button v-if="!hasAny" size="small" type="primary" @click="gotoSettings">+ 添加模型</n-button>
  <div v-else class="model-selector-group">
    <n-select
      :value="currentModel"
      :options="modelOptions"
      :placeholder="'选择模型'"
      @update:value="onModelChange"
      :consistent-menu-width="false"
      class="model-select"
      size="small"
    />
    <n-select
      :value="currentReasoning"
      :options="REASONING_OPTIONS"
      @update:value="onReasoningChange"
      :consistent-menu-width="false"
      class="reasoning-select"
      size="small"
    />
  </div>
</template>

<style scoped>
.model-selector-group {
  display: inline-flex;
  align-items: stretch;
  gap: 4px;
  flex-shrink: 0;
  height: 32px;
  background: transparent;
  border: none;
}
.model-select {
  width: 130px;
  flex-shrink: 0;
}
.reasoning-select {
  width: 60px;
  flex-shrink: 0;
}
:deep(.n-base-selection),
:deep(.n-base-selection:hover),
:deep(.n-base-selection:focus),
:deep(.n-base-selection.n-base-selection--focus),
:deep(.n-base-selection.n-base-selection--active) {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
:deep(.n-base-selection .n-base-selection__border),
:deep(.n-base-selection .n-base-selection__state-border) {
  border: none !important;
}
:deep(.n-base-selection) {
  padding-left: 4px !important;
  padding-right: 4px !important;
}
</style>