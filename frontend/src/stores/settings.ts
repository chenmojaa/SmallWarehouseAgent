import { defineStore } from 'pinia'
import { listModels, saveLlmConfig, type ModelsInfo } from '@/api/settings'
import { getApiKey, setApiKey as saveApiKey } from '@/api/client'

type Theme = 'dark' | 'light'
const THEME_KEY = 'hear_theme'

function loadTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY)
    return t === 'light' ? 'light' : 'dark'
  } catch { return 'dark' }
}

function applyTheme(t: Theme) {
  try {
    if (t === 'light') document.documentElement.classList.add('light')
    else document.documentElement.classList.remove('light')
  } catch {}
}

interface State {
  info: ModelsInfo | null
  loading: boolean
  error: string | null
  selectedProvider: string | null
  selectedModel: string | null
  apiKey: string
  apiKeySet: boolean
  theme: Theme
  /** UI: settings drawer visibility. Centralised so any component
   * (ModelSelector, sidebar, command palette…) can open it. */
  uiSettingsOpen: boolean
}

export const useSettingsStore = defineStore('settings', {
  state: (): State => ({
    info: null,
    loading: false,
    error: null,
    selectedProvider: null,
    selectedModel: null,
    apiKey: '',
    apiKeySet: false,
    theme: 'dark',
    uiSettingsOpen: false,
  }),
  actions: {
    init() {
      const k = getApiKey()
      this.apiKeySet = !!k
      this.apiKey = k ? maskKey(k) : ''
      this.theme = loadTheme()
      applyTheme(this.theme)
      // Best-effort: mirror an existing local key to the server so background
      // jobs (Feishu auto re-vectorization) have credentials without the user
      // re-saving. Never blocks UI.
      if (k) {
        saveLlmConfig({ api_key: k }).catch(() => {})
      }
    },
    async fetch() {
      this.loading = true
      this.error = null
      try {
        this.info = await listModels()
      } catch (e) {
        this.error = (e as Error)?.message || String(e)
      } finally {
        this.loading = false
      }
    },
    selectProvider(p: string | null) { this.selectedProvider = p },
    selectModel(m: string | null) { this.selectedModel = m },
    saveApiKey(k: string) {
      saveApiKey(k.trim())
      const trimmed = k.trim()
      this.apiKeySet = !!trimmed
      this.apiKey = maskKey(trimmed)
      // Mirror to the server so background jobs can embed.
      if (trimmed) saveLlmConfig({ api_key: trimmed }).catch(() => {})
    },
    clearApiKey() {
      saveApiKey('')
      this.apiKeySet = false
      this.apiKey = ''
    },
    persist() {
      // Persist current settings to backend. Provider/model/embedding changes
      // are not yet wired through the backend (no saveLlmConfig({ llm_provider })
      // exists in @/api/settings), so persist() currently only re-syncs the api_key.
      return import('@/api/settings').then(m =>
        m.saveLlmConfig({ api_key: this.apiKey }).catch(() => {})
      )
    },
    setTheme(t: Theme) {
      this.theme = t
      try { localStorage.setItem(THEME_KEY, t) } catch {}
      applyTheme(t)
    },
    toggleTheme() {
      this.setTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
    /** Open the Settings drawer. Safe to call from anywhere. */
    openSettings() {
      this.uiSettingsOpen = true
    },
    /** Close the Settings drawer. */
    closeSettings() {
      this.uiSettingsOpen = false
    },
  },
})

function maskKey(k: string): string {
  if (!k) return ''
  if (k.length <= 8) return '*'.repeat(k.length)
  return k.slice(0, 4) + '...' + k.slice(-4)
}