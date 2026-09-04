<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { t } from '@/i18n'
import { useModelsStore, type ReasoningLevel } from '@/stores/models'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { detectModels } from '@/api/custom-models'
import { getFeishuConfig, updateFeishuConfig, testFeishuConnection } from '@/api/feishu'
import { exportMyData, deleteMyAccount } from '@/api/auth'
import { setLocale, getLocale } from '@/i18n'
import {
  NInput, NButton, NTag, NEmpty, NPopconfirm, NSpin, NSwitch, NModal,
  useMessage,
} from 'naive-ui'
import SettingsOperations from './SettingsOperations.vue'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const models = useModelsStore()
const settings = useSettingsStore()
const auth = useAuthStore()
const message = useMessage()


const section = ref<'profile' | 'models' | 'knowledge' | 'appearance' | 'operations'>('profile')

const sectionTabs = computed(() => [
  { key: 'profile', label: t('settings.profile', '个人中心', 'Profile') },
  { key: 'models', label: t('settings.models', '自定义模型', 'Custom Models') },
  { key: 'knowledge', label: t('settings.knowledge', '知识库配置', 'Knowledge Base') },
  { key: 'appearance', label: t('settings.appearance', '外观与语言', 'Appearance & Language') },
  { key: 'operations', label: t('settings.operations', '运维与权限', 'Operations & Permissions') },
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
    message.warning(t('custom_models.err.fill', '请先填写 Base URL 和 API Key', 'Fill in Base URL and API Key'))
    return
  }
  detecting.value = true
  try {
    const r = await detectModels({ base_url: formBaseUrl.value.trim(), api_key: formApiKey.value.trim() })
    detected.value = { provider: r.provider, models: r.models }
    message.info(t('custom_models.detected', `识别到 ${r.models.length} 个模型`, `Detected ${r.models.length} models`))
  } catch (e) {
    message.error((e as Error).message)
    detected.value = null
  } finally {
    detecting.value = false
  }
}

async function saveEntry() {
  if (!detected.value) {
    message.warning(t('custom_models.err.detect_first', '请先识别模型', 'Detect models first'))
    return
  }
  saving.value = true
  try {
    const ok = await models.add({
      name: formName.value.trim() || t('custom_models.unnamed', '未命名', 'Unnamed'),
      baseUrl: formBaseUrl.value.trim(),
      apiKey: formApiKey.value.trim(),
      provider: detected.value.provider,
      models: detected.value.models.map(m => ({ name: m, reasoning: 'medium' as ReasoningLevel })),
      defaultModel: detected.value.models[0] || '',
    })
    if (!ok) {
      message.error(t('custom_models.save_fail', '后端保存失败: ', 'Save failed: ') + (models.lastError || 'unknown'))
      return
    }
    message.success(t('custom_models.saved', '已写入后端: ', 'Saved to: ') + (models.filePath || 'models.json'))
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
  message[ok ? 'info' : 'error'](ok ? t('custom_models.removed', '已删除', 'Removed') : t('custom_models.remove_fail', '删除失败: ', 'Remove failed: ') + (models.lastError || 'unknown'))
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
    message.success(t('feishu.saved', '飞书配置已保存', 'Feishu config saved'))
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
    message.success(t('feishu.test_ok', `连接成功，可见 ${r.spaces.length} 个知识空间`, `Connected, ${r.spaces.length} spaces`))
  } catch (e) {
    message.error(t('feishu.test_fail', '连接失败: ', 'Connection failed: ') + (e as Error).message)
  } finally {
    feishuTesting.value = false
  }
}

// ============ 外观与语言 ============
const themeLight = computed({
  get: () => settings.theme === 'light',
  set: (v: boolean) => settings.setTheme(v ? 'light' : 'dark'),
})
const lang = ref<'zh' | 'en'>(getLocale())
function setLang(v: 'zh' | 'en') {
  lang.value = v
  setLocale(v)
  message.info(v === 'zh' ? '界面语言：中文' : 'Language: English')
}

// ============ 个人中心 ============
const maskPhone = (p: string) => p ? p.replace(/^(\d{3})\d{4}(\d{4})$/, '$1****$2') : ''

// ============ GDPR data export / delete ============
async function doExport() {
  try {
    const blob = await exportMyData() as Record<string, unknown>
    const json = JSON.stringify(blob, null, 2)
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `export-${Date.now()}.json`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    message.success(t('settings.export.ok', '已导出为 JSON 文件', 'Exported as JSON'))
  } catch (e) {
    message.error((e as Error).message)
  }
}
const deleteOpen = ref(false)
async function doDeleteAccount() {
  deleteOpen.value = false
  try {
    const r = await deleteMyAccount()
    message.success(t('settings.delete.ok', `已注销账号（清理 ${r.removed_rows} 条记录）`, `Account deleted (${r.removed_rows} rows)`))
    setTimeout(() => auth.logout(), 600)
  } catch (e) {
    message.error((e as Error).message)
  }
}
</script>

<template>
  <n-modal
    :show="show"
    @update:show="(v: boolean) => emit('update:show', v)"
    :bordered="false"
  >
    <div class="drawer-card">
      <div class="drawer-head">
        <h3>{{ t('settings.title', '设置', 'Settings') }}</h3>
        <button class="close-btn" @click="emit('update:show', false)">✕</button>
      </div>

      <div class="drawer-tabs">
        <button
          v-for="tab in sectionTabs"
          :key="tab.key"
          class="drawer-tab"
          :class="{ active: section === tab.key }"
          @click="section = tab.key as typeof section"
        >{{ tab.label }}</button>
      </div>

      <div class="drawer-body">
        <!-- ============ Profile ============ -->
        <div v-if="section === 'profile'" class="section">
          <div class="profile-row">
            <span class="key-label">{{ t('settings.profile.phone', '手机号', 'Phone') }}</span>
            <span class="val">{{ maskPhone(auth.phone) }}</span>
          </div>
          <div class="profile-row">
            <span class="key-label">{{ t('settings.profile.token', '登录令牌', 'Auth Token') }}</span>
            <span class="val mono">{{ auth.token ? auth.token.slice(0, 16) + '…' : '-' }}</span>
          </div>

          <div class="actions">
            <n-button size="small" @click="doExport">{{ t('settings.account.export', '导出我的数据', 'Export my data') }}</n-button>
            <n-popconfirm
              :show-icon="false"
              positive-text="确认"
              negative-text="取消"
              @positive-click="deleteOpen = true"
            >
              <template #trigger>
                <n-button size="small" type="error" ghost>{{ t('settings.account.delete', '注销账号', 'Delete account') }}</n-button>
              </template>
              <span>{{ t('settings.delete.warn1', '真的要注销账号吗？', 'Really delete your account?') }}</span>
            </n-popconfirm>
          </div>
        </div>

        <!-- ============ Models ============ -->
        <div v-if="section === 'models'" class="section">
          <div class="form-row">
            <label>{{ t('custom_models.name', '名称', 'Name') }}</label>
            <n-input v-model:value="formName" :placeholder="t('custom_models.placeholder.name', '可选，自定义名称', 'optional')" />
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
            <n-button :loading="detecting" @click="doDetect">{{ t('custom_models.detect', '识别模型', 'Detect') }}</n-button>
            <n-button v-if="detected" :loading="saving" type="primary" @click="saveEntry">
              {{ t('custom_models.save', '保存', 'Save') }} ({{ detected.models.length }})
            </n-button>
          </div>

          <div v-if="detected" class="detected-list">
            <n-tag v-for="m in detected.models" :key="m" size="small" style="margin: 2px;">{{ m }}</n-tag>
          </div>

          <div class="hr" />

          <h4>{{ t('settings.models', '自定义模型', 'Custom Models') }}</h4>
          <n-empty v-if="models.list.length === 0" :description="t('custom_models.none', '暂无配置', 'No models yet')" />
          <div v-else class="entries">
            <div v-for="entry in models.list" :key="entry.id" class="entry">
              <div class="entry-head">
                <strong>{{ entry.name }}</strong>
                <span class="muted">{{ entry.provider }} · {{ entry.models.length }} {{ t('custom_models.models', '个模型', 'models') }}</span>
              </div>
              <div class="entry-base">{{ entry.baseUrl }}</div>
              <n-button size="tiny" type="error" ghost @click="removeEntry(entry.id)">
                {{ t('common.delete', '删除', 'Delete') }}
              </n-button>
            </div>
          </div>
        </div>

        <!-- ============ Knowledge / Feishu ============ -->
        <div v-if="section === 'knowledge'" class="section knowledge-section">
          <n-spin :show="feishuLoading">
            <div class="form-row">
              <label>Web URL</label>
              <n-input v-model:value="feishuWebUrl" placeholder="https://example.feishu.cn" />
            </div>
            <div class="form-row">
              <label>App ID</label>
              <n-input v-model:value="feishuAppId" />
            </div>
            <div class="form-row">
              <label>App Secret</label>
              <n-input v-model:value="feishuAppSecret" type="password" show-password-on="click"
                       :placeholder="feishuSecretSet ? feishuSecretMasked : t('feishu.secret_ph', '请输入', 'Enter')" />
            </div>
            <div class="form-row">
              <label>API Base</label>
              <n-input v-model:value="feishuApiBase" placeholder="https://open.feishu.cn" />
            </div>
            <div class="form-row">
              <label>Space IDs</label>
              <n-input v-model:value="feishuSpaceIds" placeholder="spc1, spc2, ..." />
            </div>
            <div class="actions">
              <n-button :loading="feishuSaving" type="primary" @click="saveFeishuConfig">{{ t('common.save', '保存', 'Save') }}</n-button>
              <n-button :loading="feishuTesting" @click="testFeishu">{{ t('feishu.test', '测试连接', 'Test') }}</n-button>
            </div>
            <div v-if="feishuConfigured" class="status-ok">✓ {{ t('feishu.configured', '已配置', 'Configured') }}</div>
            <div v-if="feishuTestSpaces.length" class="spaces">
              <n-tag v-for="sp in feishuTestSpaces" :key="sp.space_id" size="small">{{ sp.name || sp.space_id }}</n-tag>
            </div>
          </n-spin>
        </div>

        <!-- ============ Appearance & Language ============ -->
        <div v-if="section === 'appearance'" class="section">
          <div class="form-row">
            <label>{{ t('settings.theme.label', '主题', 'Theme') }}</label>
            <n-switch v-model:value="themeLight">
              <template #checked>{{ t('settings.theme.light', '浅色', 'Light') }}</template>
              <template #unchecked>{{ t('settings.theme.dark', '深色', 'Dark') }}</template>
            </n-switch>
          </div>
          <div class="form-row">
            <label>{{ t('settings.lang.label', '语言', 'Language') }}</label>
            <div class="lang-toggle">
              <button class="lang-btn" :class="{ active: lang === 'zh' }" @click="setLang('zh')">{{ t('settings.lang.zh', '中文', 'Chinese') }}</button>
              <button class="lang-btn" :class="{ active: lang === 'en' }" @click="setLang('en')">English</button>
            </div>
          </div>
        </div>        <div v-if="section === 'operations'" class="section">
          <SettingsOperations />
        </div>

      </div>

      <!-- Delete account confirmation modal -->
      <n-modal :show="deleteOpen" @update:show="(v) => deleteOpen = v">
        <div style="padding: 24px;">
          <h3>{{ t('settings.delete.title', '⚠️ 永久注销账号', '⚠️ Permanently delete account') }}</h3>
          <p>{{ t('settings.delete.body1', '此操作不可撤销。将永久删除你的账号、所有笔记、所有会话、所有记忆。', 'This cannot be undone. Your account, all notes, all sessions, and all memory will be permanently deleted.') }}</p>
          <p><strong>{{ t('settings.delete.body2', '请先导出一份数据备份。', 'Please export your data first as a backup.') }}</strong></p>
          <div style="display: flex; gap: 8px; justify-content: flex-end;">
            <n-button @click="deleteOpen = false">{{ t('common.cancel', '取消', 'Cancel') }}</n-button>
            <n-button type="error" @click="doDeleteAccount">{{ t('settings.delete.confirm', '我已备份，确认永久删除', 'I have a backup, delete now') }}</n-button>
          </div>
        </div>
      </n-modal>
    </div>
  </n-modal>
</template>

<style scoped>
.drawer-card {
  background: var(--bg-elevated);
  width: min(680px, 96vw);
  /* 固定高度：切换 tab 时弹窗尺寸保持一致，内容在 body 内滚动 */
  height: min(720px, 82vh);
  margin: 9vh auto;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 12px 48px rgba(0,0,0,0.25);
}
.drawer-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-soft); }
.drawer-head h3 { margin: 0; font-size: 16px; }
.close-btn { width: 28px; height: 28px; border: 0; background: transparent; cursor: pointer; font-size: 18px; border-radius: 999px; color: var(--text-secondary); }
.close-btn:hover { background: var(--hover-bg); }
.drawer-tabs { display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--border-soft); justify-content: flex-end; }
.drawer-tab { padding: 6px 12px; border: 0; background: transparent; border-radius: 999px; cursor: pointer; color: var(--text-secondary); font-size: 13px; }
.drawer-tab:hover { background: var(--hover-bg); }
.drawer-tab.active { background: rgba(59,130,246,0.18); color: var(--text-primary); }
.drawer-body { flex: 1; overflow-y: auto; padding: 16px 18px; }
.section { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row label { font-size: 12px; color: var(--text-secondary); }
/* 知识库配置：表单行间距放宽，按钮组与输入框拉开距离 */
.knowledge-section .n-spin-content { display: flex; flex-direction: column; gap: 26px; }
.knowledge-section .form-row { gap: 10px; }
.knowledge-section .actions { margin-top: 8px; gap: 14px; }
.knowledge-section .status-ok, .knowledge-section .spaces { margin: 0; }
.profile-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px dashed var(--border-soft); }
.key-label { color: var(--text-secondary); font-size: 13px; }
.val { font-size: 13px; color: var(--text-primary); }
.val.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.detected-list { display: flex; flex-wrap: wrap; gap: 4px; }
.entries { display: flex; flex-direction: column; gap: 8px; }
.entry { padding: 10px 12px; border: 1px solid var(--border-soft); border-radius: 8px; }
.entry-head { display: flex; justify-content: space-between; align-items: center; }
.muted { color: var(--text-secondary); font-size: 12px; }
.entry-base { color: var(--text-muted); font-size: 12px; font-family: ui-monospace, monospace; }
.hr { height: 1px; background: var(--border-soft); margin: 8px 0; }
.status-ok { color: var(--success-color, #22c55e); font-size: 12px; }
.spaces { display: flex; gap: 4px; flex-wrap: wrap; }
.lang-toggle { display: inline-flex; gap: 4px; padding: 2px; border: 1px solid var(--border-soft); border-radius: 999px; }
.lang-btn { padding: 4px 12px; border: 0; background: transparent; border-radius: 999px; cursor: pointer; color: var(--text-secondary); font-size: 13px; }
.lang-btn.active { background: rgba(59,130,246,0.18); color: var(--text-primary); }
</style>