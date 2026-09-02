<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useModelsStore, type ReasoningLevel } from '@/stores/models'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { detectModels } from '@/api/custom-models'
import { getFeishuConfig, updateFeishuConfig, testFeishuConnection } from '@/api/feishu'
import {
  NInput, NButton, NTag, NEmpty, NPopconfirm, NSpin, NSwitch, NModal,
  useMessage,
} from 'naive-ui'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const models = useModelsStore()
const settings = useSettingsStore()
const auth = useAuthStore()
const message = useMessage()

const section = ref<'profile' | 'models' | 'knowledge' | 'appearance'>('profile')

const sectionTabs = computed(() => [
  { key: 'profile', label: '个人中心' },
  { key: 'models', label: '自定义模型' },
  { key: 'knowledge', label: '知识库配置' },
  { key: 'appearance', label: '外观与语言' },
])

watch(() => props.show, (v) => {
  if (v) {
    settings.init()
    if (section.value === 'knowledge') loadFeishuConfig()
  }
})

// ============ 模型 ============
const formName = ref('')
const formBaseUrl = ref('')
const formApiKey = ref('')
const detecting = ref(false)
const saving = ref(false)
const detected = ref<{ provider: string; models: string[] } | null>(null)

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

// ============ 知识库（飞书） ============
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
    feishuAppSecret.value = ''
  } catch {
    // silent fail - config may not be available
  } finally {
    feishuLoading.value = false
  }
}

watch(section, (s) => {
  if (s === 'knowledge' && !feishuAppId.value && !feishuLoading.value) void loadFeishuConfig()
})

async function saveFeishuConfig() {
  feishuSaving.value = true
  try {
    const patch: Record<string, string> = {
      web_url: feishuWebUrl.value.trim(),
      app_id: feishuAppId.value.trim(),
      api_base: feishuApiBase.value.trim(),
      space_ids: feishuSpaceIds.value.trim(),
    }
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

// ============ 外观与语言 ============
const themeLight = computed({
  get: () => settings.theme === 'light',
  set: (v: boolean) => settings.setTheme(v ? 'light' : 'dark'),
})
const lang = ref<'zh' | 'en'>((localStorage.getItem('app_lang') as 'zh' | 'en') || 'zh')
function setLang(v: 'zh' | 'en') {
  lang.value = v
  try { localStorage.setItem('app_lang', v) } catch {}
  message.info(v === 'zh' ? '当前界面语言：中文（部分内容跟随系统）' : 'UI language: Chinese (partial)')
}

// ============ 个人中心 ============
const maskPhone = (p: string) => p ? p.replace(/^(\d{3})\d{4}(\d{4})$/, '$1****$2') : ''
</script>

<template>
  <n-modal
    :show="show"
    @update:show="(v: boolean) => emit('update:show', v)"
    :bordered="false"
  >
    <div class="drawer-card">
      <div class="drawer-head">
        <h3>设置</h3>
        <button class="close-btn" @click="emit('update:show', false)">✕</button>
      </div>

      <div class="drawer-body">
        <!-- 左侧导航 -->
        <nav class="drawer-nav">
          <button
            v-for="t in sectionTabs"
            :key="t.key"
            class="nav-item"
            :class="{ active: section === t.key }"
            @click="section = t.key as any"
          >
            {{ t.label }}
          </button>
        </nav>

        <!-- 右侧内容 -->
        <div class="drawer-content">
          <!-- 个人中心 -->
          <div v-if="section === 'profile'" class="pane">
            <h4 class="pane-title">个人中心</h4>
            <div class="profile-card">
              <div class="avatar">{{ (auth.phone || '?').slice(-1) }}</div>
              <div class="profile-info">
                <strong>{{ auth.phone }}</strong>
                <span class="muted">账号 {{ maskPhone(auth.phone) }} · 已登录</span>
              </div>
            </div>
            <div class="info-rows">
              <div class="info-row">
                <span class="info-label">主题</span>
                <n-switch v-model:value="themeLight" size="small">
                  <template #checked>白昼</template>
                  <template #unchecked>黑夜</template>
                </n-switch>
              </div>
              <div class="info-row">
                <span class="info-label">当前模型</span>
                <n-tag size="small" :bordered="false">{{ models.selected?.modelName || '默认' }}</n-tag>
              </div>
              <div class="info-row">
                <span class="info-label">自定义模型</span>
                <span class="muted">{{ models.list.length }} 个</span>
              </div>
              <div class="info-row">
                <span class="info-label">飞书知识库</span>
                <n-tag size="small" :bordered="false" :type="feishuConfigured ? 'success' : 'default'">
                  {{ feishuConfigured ? '已配置' : '未配置' }}
                </n-tag>
              </div>
            </div>
          </div>

          <!-- 自定义模型 -->
          <div v-else-if="section === 'models'" class="pane">
            <h4 class="pane-title">添加自定义 LLM</h4>
            <div class="form-grid">
              <n-input v-model:value="formName" placeholder="名称" />
              <n-input v-model:value="formBaseUrl" placeholder="例：https://api.openai.com/v1" />
              <n-input v-model:value="formApiKey" type="password" show-password-on="click" placeholder="API Key" />
              <div class="btn-row">
                <n-button size="small" :loading="detecting" @click="doDetect">识别模型</n-button>
                <n-button size="small" type="primary" :disabled="!detected" @click="saveEntry">保存为可选项</n-button>
              </div>
            </div>
            <div v-if="detected" class="detected-box">
              <span style="font-size: 13px">识别到 {{ detected.models.length }} 个模型 · {{ detected.provider }}</span>
              <div class="model-list">
                <code v-for="m in detected.models" :key="m">{{ m }}</code>
              </div>
            </div>

            <h4 class="pane-title" style="margin-top: 20px">已添加的 LLM</h4>
            <n-empty v-if="models.list.length === 0" size="small" description="还没有自定义 LLM" />
            <div v-else class="llm-list">
              <div v-for="e in models.list" :key="e.id" class="llm-item">
                <div class="llm-main">
                  <strong>{{ e.name }}</strong>
                  <span class="llm-meta">{{ e.provider }} · {{ e.baseUrl }}</span>
                </div>
                <n-popconfirm @positive-click="removeEntry(e.id)">
                  <template #trigger>
                    <n-button text size="small" type="error">删除</n-button>
                  </template>
                  删除该 LLM？
                </n-popconfirm>
              </div>
            </div>
          </div>

          <!-- 知识库配置 -->
          <div v-else-if="section === 'knowledge'" class="pane">
            <div class="pane-head-row">
              <h4 class="pane-title" style="margin: 0">飞书知识库配置</h4>
              <n-tag size="small" :type="feishuConfigured ? 'success' : 'default'">
                {{ feishuConfigured ? '已配置' : '未配置' }}
              </n-tag>
            </div>
            <p class="muted small">连接你自己的飞书应用，把知识库文档同步进来</p>
            <n-spin :show="feishuLoading" size="small">
              <div class="form-grid">
                <n-input v-model:value="feishuAppId" placeholder="App ID（飞书开放平台 → 应用凭证）" />
                <n-input
                  v-model:value="feishuAppSecret"
                  type="password"
                  show-password-on="click"
                  :placeholder="feishuSecretSet ? '已保存：' + feishuSecretMasked + '（留空则保持不变）' : 'App Secret'"
                />
                <n-input v-model:value="feishuApiBase" placeholder="API 域名，默认 https://open.feishu.cn" />
                <n-input v-model:value="feishuSpaceIds" placeholder="知识空间 ID，逗号分隔（留空 = 同步全部可见空间）" />
                <n-input v-model:value="feishuWebUrl" placeholder="查看域名，例：https://xxx.feishu.cn（用于生成文档查看链接）" />
                <div class="btn-row">
                  <n-button size="small" type="primary" :loading="feishuSaving" @click="saveFeishuConfig">保存飞书配置</n-button>
                  <n-button size="small" :loading="feishuTesting" :disabled="!feishuConfigured" @click="testFeishu">测试连接</n-button>
                </div>
              </div>
            </n-spin>
            <div v-if="feishuTestSpaces.length" class="detected-box">
              <span style="font-size: 13px">可见的知识空间（{{ feishuTestSpaces.length }}）</span>
              <div class="model-list">
                <code v-for="s in feishuTestSpaces" :key="s.space_id">{{ s.name || '(未命名)' }} · {{ s.space_id }}</code>
              </div>
            </div>
          </div>

          <!-- 外观与语言 -->
          <div v-else class="pane">
            <h4 class="pane-title">外观</h4>
            <div class="info-row">
              <span class="info-label">白昼模式</span>
              <n-switch v-model:value="themeLight" size="small" />
            </div>
            <p class="muted small">关闭则使用黑夜模式（跟随顶栏 ☀/☾ 按钮联动）</p>

            <h4 class="pane-title" style="margin-top: 20px">语言</h4>
            <div class="lang-row">
              <button class="lang-btn" :class="{ active: lang === 'zh' }" @click="setLang('zh')">简体中文</button>
              <button class="lang-btn" :class="{ active: lang === 'en' }" @click="setLang('en')">English</button>
            </div>
            <p class="muted small">助手回答语言始终跟随你的提问语言（由后端提示词约束）</p>
          </div>
        </div>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.drawer-card {
  width: min(680px, calc(100vw - 32px));
  background: var(--bg-elevated, #fff);
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15, 23, 42, .22);
}
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px 12px;
  border-bottom: 1px solid var(--border-soft);
}
.drawer-head h3 { margin: 0; font-size: 17px; font-weight: 700; }
.close-btn {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 15px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}
.close-btn:hover { background: var(--hover-bg); color: var(--text-primary); }
.drawer-body { display: flex; min-height: 380px; max-height: min(640px, calc(100vh - 160px)); }
.drawer-nav {
  width: 148px;
  flex-shrink: 0;
  padding: 14px 10px;
  border-right: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nav-item {
  display: block;
  text-align: left;
  padding: 9px 12px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
}
.nav-item:hover { background: var(--hover-bg); color: var(--text-primary); }
.nav-item.active {
  background: rgba(59, 130, 246, .10);
  color: #3b82f6;
  font-weight: 600;
}
.drawer-content {
  flex: 1;
  min-width: 0;
  padding: 18px 22px;
  overflow-y: auto;
}
.pane-title { margin: 0 0 12px; font-size: 14px; font-weight: 600; }
.pane-head-row { display: flex; align-items: center; justify-content: space-between; }
.muted { color: var(--text-muted); }
.small { font-size: 12px; margin: 6px 0 12px; }
.form-grid { display: flex; flex-direction: column; gap: 10px; }
.btn-row { display: flex; gap: 8px; }
.detected-box {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--hover-bg);
}
.model-list { display: grid; gap: 3px; margin-top: 8px; }
.model-list code { font-size: 12px; color: var(--text-secondary); word-break: break-all; }
.llm-list { display: flex; flex-direction: column; gap: 8px; }
.llm-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--bg-app, transparent);
}
.llm-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.llm-main strong { font-size: 13px; }
.llm-meta { font-size: 11px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.profile-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(59, 130, 246, .08), rgba(56, 189, 248, .04));
  margin-bottom: 14px;
}
.avatar {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #3b82f6, #38bdf8);
  flex-shrink: 0;
}
.profile-info { display: flex; flex-direction: column; gap: 3px; }
.profile-info strong { font-size: 15px; }
.info-rows { display: flex; flex-direction: column; gap: 0; border: 1px solid var(--border-soft); border-radius: 12px; overflow: hidden; }
.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
}
.info-row + .info-row { border-top: 1px solid var(--border-soft); }
.info-label { font-size: 13px; color: var(--text-secondary); }
.lang-row { display: flex; gap: 10px; }
.lang-btn {
  flex: 1;
  padding: 10px 14px;
  border: 1.5px solid var(--border-soft);
  border-radius: 10px;
  background: var(--bg-app, transparent);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
}
.lang-btn:hover { border-color: #3b82f6; }
.lang-btn.active { border-color: #3b82f6; background: rgba(59, 130, 246, .08); color: #3b82f6; font-weight: 600; }
@media (max-width: 560px) {
  .drawer-body { flex-direction: column; }
  .drawer-nav { width: auto; flex-direction: row; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--border-soft); }
  .nav-item { white-space: nowrap; }
}

.setting-row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border-soft, rgba(255,255,255,0.08)); }
.setting-row:last-child { border-bottom: 0; }
.setting-row label { min-width: 100px; font-size: 13px; opacity: 0.85; }
.accent-row { display: flex; gap: 8px; flex-wrap: wrap; }
.accent-swatch { width: 24px; height: 24px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; transition: transform 0.15s, border-color 0.15s; }
.accent-swatch:hover { transform: scale(1.15); }
.accent-swatch.active { border-color: var(--text-primary, #fff); box-shadow: 0 0 0 2px var(--bg-app, #1f1f23) inset; }
</style>
