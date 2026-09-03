<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useModelsStore, type ReasoningLevel } from '@/stores/models'
import { detectModels } from '@/api/custom-models'
import { NSelect, NButton, NInput, NModal, NTag, useMessage } from 'naive-ui'

const models = useModelsStore()
const message = useMessage()

const DEBUG = import.meta.env.DEV
function dbg(...args: unknown[]) { if (DEBUG) console.debug("[ModelSelector]", ...args) }

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

// ===== Inline add-model dialog =====
const addOpen = ref(false)
const formName = ref('')
const formBaseUrl = ref('')
const formApiKey = ref('')
const detecting = ref(false)
const saving = ref(false)
const detected = ref<{ provider: string; models: string[] } | null>(null)

function openAdd() {
  // Pre-fill Base URL from any previously saved key/url so re-adding is fast.
  addOpen.value = true
  detected.value = null
  formName.value = ''
  formBaseUrl.value = ''
  formApiKey.value = ''
}

async function doDetect() {
  if (!formBaseUrl.value.trim() || !formApiKey.value.trim()) {
    message.warning('请先填写 Base URL 和 API Key')
    return
  }
  detecting.value = true
  try {
    const r = await detectModels({ base_url: formBaseUrl.value.trim(), api_key: formApiKey.value.trim() })
    detected.value = { provider: r.provider, models: r.models }
    message.info(`识别到 ${r.models.length} 个模型`)
  } catch (e) {
    message.error((e as Error).message)
    detected.value = null
  } finally {
    detecting.value = false
  }
}

async function saveEntry() {
  if (!detected.value) {
    message.warning('请先识别模型')
    return
  }
  saving.value = true
  try {
    const ok = await models.add({
      name: formName.value.trim() || '未命名',
      baseUrl: formBaseUrl.value.trim(),
      apiKey: formApiKey.value.trim(),
      provider: detected.value.provider,
      models: detected.value.models.map(m => ({ name: m, reasoning: 'medium' as ReasoningLevel })),
      defaultModel: detected.value.models[0] || '',
    })
    if (!ok) {
      message.error('后端保存失败: ' + (models.lastError || 'unknown'))
      return
    }
    message.success('已添加 ' + (detected.value.models[0] || formName.value || '模型'))
    addOpen.value = false
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <!-- Empty state: single CTA that actually opens an add-model dialog -->
  <n-button v-if="!hasAny" size="small" type="primary" @click="openAdd">+ 添加模型</n-button>

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

  <!-- ===== Add Model dialog ===== -->
  <n-modal
    :show="addOpen"
    @update:show="(v) => addOpen = v"
    :mask-closable="!detecting && !saving"
    preset="card"
    title="添加模型"
    style="width: 460px; max-width: 92vw;"
  >
    <div class="add-form">
      <div class="form-row">
        <label>名称 <span class="hint">（可选）</span></label>
        <n-input v-model:value="formName" placeholder="给这套配置起个名字" />
      </div>
      <div class="form-row">
        <label>Base URL</label>
        <n-input v-model:value="formBaseUrl" placeholder="https://api.example.com/v1" />
      </div>
      <div class="form-row">
        <label>API Key</label>
        <n-input v-model:value="formApiKey" type="password" show-password-on="click" />
      </div>
      <div class="actions">
        <n-button :loading="detecting" @click="doDetect">识别模型</n-button>
        <n-button v-if="detected" :loading="saving" type="primary" @click="saveEntry">
          保存（{{ detected.models.length }}）
        </n-button>
      </div>
      <div v-if="detected" class="detected-list">
        <n-tag v-for="m in detected.models" :key="m" size="small" style="margin: 2px;">{{ m }}</n-tag>
      </div>
    </div>
  </n-modal>
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
  /* grow to fit the longest model name, never clip */
  flex: 1 1 auto;
  min-width: 160px;
  max-width: 280px;
}
.reasoning-select {
  flex: 0 0 auto;
  width: 88px;
}
/* Centre the rendered label inside n-select (default is left-aligned). */
.model-selector-group :deep(.n-base-selection-input) {
  justify-content: center;
  text-align: center;
}
.model-selector-group :deep(.n-base-selection-input__content) {
  font-size: 13px;
  line-height: 1.2;
  text-align: center;
  width: 100%;
}
.add-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-row label {
  font-size: 12px;
  color: var(--text-secondary);
}
.form-row .hint {
  color: var(--text-muted);
  font-weight: normal;
}
.actions {
  display: flex;
  gap: 8px;
}
.detected-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
  background: var(--hover-bg, rgba(255,255,255,0.04));
  border-radius: 6px;
}
</style>