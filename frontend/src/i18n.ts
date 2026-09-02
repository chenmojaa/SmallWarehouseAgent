// Minimal i18n: t('key', zh, en) → zh-CN by default, switchable via settings.
// Usage in components:
//   import < t > from '@/i18n'
//   <h1>{t('app.title')}</h1>
//   <h1>{t('app.title', '个人知识小助手', 'Second Brain')}</h1>

import { ref } from 'vue'

const STORAGE_KEY = 'hd_locale'
const DEFAULT_LOCALE = 'zh'

export type Locale = 'zh' | 'en'

const locale = ref<Locale>(((typeof localStorage !== 'undefined' && (localStorage.getItem(STORAGE_KEY) as Locale)) || DEFAULT_LOCALE) as Locale)

export function setLocale(l: Locale) {
  locale.value = l
  try { localStorage.setItem(STORAGE_KEY, l) } catch {}
  document.documentElement.lang = l === 'zh' ? 'zh-CN' : 'en'
}

export function getLocale(): Locale {
  return locale.value
}

export const t = (key: string, zh: string, en?: string): string => {
  // simple key→value map; if key matches a registered translation, prefer that
  const reg = (translations as Record<string, { zh: string; en: string }>)[key]
  if (reg) return locale.value === 'en' ? reg.en : reg.zh
  // fallback to inline zh/en args
  return locale.value === 'en' ? (en || zh) : zh
}

// Default translations for common keys.
export const translations: Record<string, { zh: string; en: string }> = {
  'app.title': { zh: 'smallhouse', en: 'Second Brain' },
  'app.subtitle': { zh: '个人知识小助手', en: 'Personal Knowledge Assistant' },
  'nav.chat': { zh: '新对话', en: 'New Chat' },
  'nav.notes': { zh: '知识库', en: 'Knowledge Base' },
  'nav.skills': { zh: '技能 / MCP', en: 'Skills / MCP' },
  'nav.settings': { zh: '设置', en: 'Settings' },
  'nav.logout': { zh: '退出', en: 'Logout' },
  'search.placeholder': { zh: '输入消息，回车发送，Shift+Enter 换行', en: 'Type a message, Enter to send' },
  'search.send': { zh: '发送', en: 'Send' },
  'plan.enabled': { zh: '任务规划已开启', en: 'Planning on' },
  'plan.disabled': { zh: '任务规划已关闭', en: 'Planning off' },
  'rag.on': { zh: 'RAG 开启', en: 'RAG on' },
  'rag.off': { zh: 'RAG 关闭', en: 'RAG off' },
  'palette.title': { zh: '搜索命令、会话或操作…', en: 'Search commands, sessions, or actions…' },
  'palette.empty': { zh: '没有匹配的命令', en: 'No matching commands' },
  'palette.footer.updown': { zh: '选择', en: 'Select' },
  'palette.footer.enter': { zh: '执行', en: 'Run' },
  'palette.footer.esc': { zh: '关闭', en: 'Close' },
  'mcp.title': { zh: 'MCP 让模型拥有「超能力」', en: 'Give your model superpowers' },
  'mcp.subtitle': { zh: '把本地命令、HTTP API、知识图谱注册成可调用的工具。', en: '把本地命令、HTTP API、知识图谱注册成可调用的工具。' },
  'mcp.tab.presets': { zh: '预设', en: 'Presets' },
  'mcp.tab.servers': { zh: '已配置', en: 'Configured' },
  'mcp.tab.history': { zh: '调用历史', en: 'Call History' },
  'settings.title': { zh: '设置', en: 'Settings' },
  'settings.profile': { zh: '个人中心', en: 'Profile' },
  'settings.models': { zh: '自定义模型', en: 'Custom Models' },
  'settings.knowledge': { zh: '知识库配置', en: 'Knowledge Base' },
  'settings.appearance': { zh: '外观与语言', en: 'Appearance & Language' },
  'theme.dark': { zh: '深色', en: 'Dark' },
  'theme.light': { zh: '浅色', en: 'Light' },
  'lang.zh': { zh: '中文', en: 'Chinese' },
  'lang.en': { zh: '英文', en: 'English' },
  'common.cancel': { zh: '取消', en: 'Cancel' },
  'common.confirm': { zh: '确定', en: 'Confirm' },
  'common.delete': { zh: '删除', en: 'Delete' },
  'common.save': { zh: '保存', en: 'Save' },
  'common.loading': { zh: '加载中…', en: 'Loading…' },
}

export default { t, setLocale, getLocale, translations }