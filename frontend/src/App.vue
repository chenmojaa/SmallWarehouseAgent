<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NConfigProvider, NLayout, NLayoutHeader, NLayoutSider, NLayoutContent,
  NMessageProvider, NSpace, NText, NButton, darkTheme, lightTheme,
} from 'naive-ui'
import { useSettingsStore } from '@/stores/settings'
import { useSessionsStore } from '@/stores/sessions'
import { useModelsStore } from '@/stores/models'
import { useAuthStore } from '@/stores/auth'
import ChatHistory from '@/components/ChatHistory.vue'
import StreamingIndicator from '@/components/StreamingIndicator.vue'
import SettingsDrawer from '@/components/SettingsDrawer.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isLoginPage = computed(() => route.name === 'login')

const BRAND_BLUE = '#3b82f6'
const naiveOverrides = computed(() => ({
  common: {
    primaryColor: BRAND_BLUE,
    primaryColorHover: '#60a5fa',
    primaryColorPressed: '#2563eb',
    primaryColorSuppl: BRAND_BLUE,
    infoColor: BRAND_BLUE,
    infoColorHover: '#60a5fa',
    infoColorPressed: '#2563eb',
    successColor: BRAND_BLUE,
    successColorHover: '#60a5fa',
    successColorPressed: '#2563eb',
  },
}))

const settings = useSettingsStore()
const sessions = useSessionsStore()
const models = useModelsStore()

const naiveTheme = computed(() => settings.theme === 'light' ? lightTheme : darkTheme)

let retryTimer: number | null = null
function retryFailedLoads() {
  if (sessions.error) sessions.load()
  if (models.lastError) models.loadFromBackend()
}

onMounted(() => {
  // init 应用主题与本地 key 状态（登录页也需要主题）
  settings.init()
  if (isLoginPage.value) return
  settings.fetch()
  sessions.load()
  models.loadFromBackend()
  retryTimer = window.setInterval(retryFailedLoads, 8000)
})

// 登录成功后从登录页进入应用时，再执行初始化加载
watch(isLoginPage, (nowLogin, wasLogin) => {
  if (wasLogin && !nowLogin) {
    settings.init()
    settings.fetch()
    sessions.load()
    models.loadFromBackend()
    if (retryTimer === null) retryTimer = window.setInterval(retryFailedLoads, 8000)
  }
})

function handleLogout() {
  auth.logout()
  router.replace('/login')
}

onBeforeUnmount(() => {
  if (retryTimer !== null) window.clearInterval(retryTimer)
})

watch(() => settings.theme, () => { /* applied via setTheme */ })

function toggleTheme() {
  settings.toggleTheme()
}

const siderCollapsed = ref(false)
function toggleSider() {
  siderCollapsed.value = !siderCollapsed.value
}

// 设置弹窗
const settingsOpen = ref(false)
</script>

<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="naiveOverrides">
    <n-message-provider>
      <!-- 登录页：独立全屏视图，不渲染主布局 -->
      <router-view v-if="isLoginPage" />

      <n-layout v-else style="height: 100vh">
        <n-layout-header bordered style="padding: 8px 16px; display: flex; align-items: center; justify-content: space-between; height: 48px">
          <n-space align="center">
            <button
              class="sider-toggle"
              :title="siderCollapsed ? '展开侧边栏' : '收起侧边栏'"
              @click="toggleSider"
            >
              <svg v-if="siderCollapsed" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="3" y1="6" x2="21" y2="6"/>
                <line x1="3" y1="12" x2="21" y2="12"/>
                <line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="3" y1="6" x2="21" y2="6"/>
                <line x1="3" y1="12" x2="15" y2="12"/>
                <line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>
            <img src="/logo.png" alt="Small Warehouse Agent" class="brand-logo" />
            <n-text depth="3" style="font-size: 11px">v0.6</n-text>
          </n-space>
          <n-space align="center" :wrap="false">
            <button
              class="theme-toggle"
              :title="settings.theme === 'dark' ? '切换到白昼' : '切换到黑夜'"
              @click="toggleTheme"
            >
              <span v-if="settings.theme === 'dark'" class="theme-icon">☀</span>
              <span v-else class="theme-icon">☾</span>
            </button>
            <router-link to="/notes" custom v-slot="{ navigate }"><n-button quaternary size="small" @click="navigate">笔记</n-button></router-link>
            <n-button quaternary size="small" @click="settingsOpen = true">设置</n-button>
            <n-text depth="3" style="font-size: 12px">{{ auth.phone }}</n-text>
            <n-button quaternary size="small" @click="handleLogout">退出</n-button>
          </n-space>
        </n-layout-header>
        <n-layout has-sider style="height: calc(100vh - 48px)">
          <n-layout-sider v-if="!siderCollapsed" bordered :width="260" :native-scrollbar="false" content-style="padding: 0;">
            <ChatHistory />
          </n-layout-sider>
          <n-layout-content content-style="padding: 0; height: 100%;">
            <router-view />
            <StreamingIndicator />
          </n-layout-content>
        </n-layout>
        <SettingsDrawer v-model:show="settingsOpen" />
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.sider-toggle {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-primary);
  padding: 0;
  transition: background 0.15s;
}
.sider-toggle:hover {
  background: var(--hover-bg);
}
.theme-toggle {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 50%;
  cursor: pointer;
  color: var(--text-primary);
  font-size: 16px;
  line-height: 1;
  padding: 0;
  transition: background 0.15s;
}
.theme-toggle:hover {
  background: var(--hover-bg);
}
.theme-icon {
  font-size: 16px;
  line-height: 1;
}
.brand-logo {
  height: 28px;
  width: auto;
  display: block;
  user-select: none;
  -webkit-user-drag: none;
}
</style>
