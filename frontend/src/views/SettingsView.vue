<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useModelsStore, type ReasoningLevel, type CustomModelEntry } from '@/stores/models'
import { useSettingsStore } from '@/stores/settings'
import { detectModels } from '@/api/custom-models'
import { getFeishuConfig, updateFeishuConfig, testFeishuConnection } from '@/api/feishu'
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

// Feishu config
const feishuWebUrl = ref('')
const feishuAppId = ref('')
const feishuAppSecret = ref('')
const feishuApiBase = ref('')
const feishuSpaceIds = ref('')
const feishuSecretSet = ref(false)
const feishuSecretMasked = ref('')
const feishuConfigured = ref(false)
const feishuLoading = ref(false)
const feishuSaving = ref(false)
const feishuTesting = ref(false)
const feishuTestSpaces = ref<{ space_id: string; name?: string }[]>([])

onMounted(() => {
  settings.init()
  loadFeishuConfig()
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

async function loadFeishuConfig() {
  feishuLoading.value = true
  try {
    const cfg = await getFeishuConfig()
    feishuWebUrl.value = cfg.web_url || ''
    feishuAppId.value = cfg.app_id || ''
    feishuApiBase.value = cfg.api_base || ''
    feishuSpaceIds.value = (cfg.space_ids || []).join(', ')
    feishuSecretSet.value = cfg.app_secret_set
    feishuSecretMasked.value = cfg.app_secret_masked || ''
    feishuConfigured.value = cfg.configured
    // Secret is never returned; leave the input empty. Placeholder shows masked value.
    feishuAppSecret.value = ''
  } catch (e) {
    // silent fail - config may not be available
  } finally {
    feishuLoading.value = false
  }
}

async function saveFeishuConfig() {
  feishuSaving.value = true
  try {
    const patch: Record<string, string> = {
      web_url: feishuWebUrl.value.trim(),
      app_id: feishuAppId.value.trim(),
      api_base: feishuApiBase.value.trim(),
      space_ids: feishuSpaceIds.value.trim(),
    }
    // Only send the secret when the user actually typed a new one.
    if (feishuAppSecret.value.trim()) {
      patch.app_secret = feishuAppSecret.value.trim()
    }
    const cfg = await updateFeishuConfig(patch)
    feishuSecretSet.value = cfg.app_secret_set
    feishuSecretMasked.value = cfg.app_secret_masked || ''
    feishuConfigured.value = cfg.configured
    feishuAppSecret.value = ''
    message.success('飞书配置已保存')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    feishuSaving.value = false
  }
}

async function testFeishu() {
  feishuTesting.value = true
  feishuTestSpaces.value = []
  try {
    const r = await testFeishuConnection()
    feishuTestSpaces.value = r.spaces || []
    message.success(`连接成功，可见 ${r.spaces.length} 个知识空间`)
  } catch (e) {
    message.error('连接失败: ' + (e as Error).message)
  } finally {
    feishuTesting.value = false
  }
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

    <n-card title="飞书知识库配置" :bordered="false">
      <n-space vertical :size="10">
        <n-space align="center" :size="6">
          <n-text depth="3" style="font-size: 12px">连接你自己的飞书应用，把知识库文档同步进来</n-text>
          <n-tag size="small" :type="feishuConfigured ? 'success' : 'default'">
            {{ feishuConfigured ? '已配置' : '未配置' }}
          </n-tag>
        </n-space>

        <n-input
          v-model:value="feishuAppId"
          placeholder="App ID（飞书开放平台 → 应用凭证）"
          :disabled="feishuLoading"
        />
        <n-input
          v-model:value="feishuAppSecret"
          type="password"
          show-password-on="click"
          :placeholder="feishuSecretSet ? '已保存：' + feishuSecretMasked + '（留空则保持不变）' : 'App Secret'"
          :disabled="feishuLoading"
        />
        <n-input
          v-model:value="feishuApiBase"
          placeholder="API 域名，默认 https://open.feishu.cn"
          :disabled="feishuLoading"
        />
        <n-input
          v-model:value="feishuSpaceIds"
          placeholder="知识空间 ID，逗号分隔（留空 = 同步全部可见空间）"
          :disabled="feishuLoading"
        />
        <n-input
          v-model:value="feishuWebUrl"
          placeholder="查看域名，例：https://xxx.feishu.cn（用于生成文档查看链接）"
          :disabled="feishuLoading"
        />

        <n-space>
          <n-button
            type="primary"
            :loading="feishuSaving"
            :disabled="feishuLoading"
            @click="saveFeishuConfig"
          >
            保存飞书配置
          </n-button>
          <n-button
            :loading="feishuTesting"
            :disabled="feishuLoading || !feishuConfigured"
            @click="testFeishu"
          >
            测试连接
          </n-button>
        </n-space>

        <div v-if="feishuTestSpaces.length" style="border-top: 1px solid var(--border-soft); padding-top: 10px">
          <n-text style="font-size: 13px">可见的知识空间（{{ feishuTestSpaces.length }}）</n-text>
          <n-space vertical :size="2" style="margin-top: 6px; padding-left: 4px">
            <n-text v-for="s in feishuTestSpaces" :key="s.space_id" style="font-family: monospace; font-size: 13px; padding: 1px 0">
              {{ s.name || '(未命名)' }} · {{ s.space_id }}
            </n-text>
          </n-space>
        </div>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.item-card {
  background: var(--bg-elevated) !important;
}
</style>