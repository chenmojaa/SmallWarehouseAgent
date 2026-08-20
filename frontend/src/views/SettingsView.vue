<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useModelsStore, type ReasoningLevel, type CustomModelEntry } from '@/stores/models'
import { useSettingsStore } from '@/stores/settings'
import { detectModels } from '@/api/custom-models'
import {
  NCard, NSpace, NText, NTag, NInput, NButton, useMessage,
  NPopconfirm, NEmpty,
} from 'naive-ui'

const models = useModelsStore()
const settings = useSettingsStore()
const message = useMessage()

const formName = ref('')
const formBaseUrl = ref('')
const formApiKey = ref('')
const detecting = ref(false)
const saving = ref(false)
const detected = ref<{ provider: string; models: string[] } | null>(null)
onMounted(() => {
  settings.init()
})

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
    message.success('已写入后端 ' + (models.filePath || 'models.json'))
    formName.value = ''
    formBaseUrl.value = ''
    formApiKey.value = ''
    detected.value = null
  } finally {
    saving.value = false
  }
}
async function removeEntry(id: string) {
  const ok = await models.remove(id)
  message[ok ? 'info' : 'error'](ok ? '已删除' : '删除失败: ' + (models.lastError || 'unknown'))
}
</script>

<template>
  <div style="height: 100%; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; padding-right: 4px">
    <n-text strong style="font-size: 16px">设置</n-text>

    <n-card title="添加自定义 LLM" :bordered="false">
      <n-space vertical :size="10">
        <n-input v-model:value="formName" placeholder="名称" />
        <n-input v-model:value="formBaseUrl" placeholder="例：https://api.openai.com/v1" />
        <n-input
          v-model:value="formApiKey"
          type="password"
          show-password-on="click"
          placeholder="API Key"
        />
        <n-space>
          <n-button :loading="detecting" @click="doDetect">识别模型</n-button>
          <n-button type="primary" :disabled="!detected" @click="saveEntry">保存为可选项</n-button>
        </n-space>
                <div v-if="detected" style="border-top: 1px solid var(--border-soft); padding-top: 10px">
          <n-text style="font-size: 13px">识别到 {{ detected.models.length }} 个模型 · {{ detected.provider }}</n-text>          
          <n-space vertical :size="2" style="margin-top: 6px; padding-left: 4px">
            <n-text v-for="m in detected.models" :key="m" style="font-family: monospace; font-size: 13px; padding: 1px 0">{{ m }}</n-text>
          </n-space>
        </div>
      </n-space>
    </n-card>

    <n-card title="已添加的 LLM" :bordered="false">
      <n-empty v-if="models.list.length === 0" description="还没有自定义 LLM" />
      <n-space vertical v-else>
        <n-card
          v-for="e in models.list"
          :key="e.id"
          :bordered="false"
          size="small"
          class="item-card"
        >
          <template #header>
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-space align="center">
                <n-text strong>{{ e.name }}</n-text>
                <n-tag size="small">{{ e.provider }}</n-tag>
                <n-tag size="small" :bordered="false">{{ e.baseUrl }}</n-tag>
              </n-space>
              <n-popconfirm @positive-click="removeEntry(e.id)">
                <template #trigger>
                  <n-button text size="small" type="error">删除</n-button>
                </template>
                删除该 LLM？
              </n-popconfirm>
            </n-space>
          </template>


        </n-card>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.item-card {
  background: var(--bg-elevated) !important;
}
</style>