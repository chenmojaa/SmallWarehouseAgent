import { ref, watch } from 'vue'

export type AccentColor = 'blue' | 'violet' | 'emerald' | 'rose' | 'amber' | 'cyan' | 'pink'
const ACCENT_KEY = 'hd_accent_color'
const THEME_KEY = 'hd_theme_v2'

export const accentColor = ref<AccentColor>(((localStorage.getItem(ACCENT_KEY) as AccentColor) || 'blue'))
export const themeMode = ref<'dark' | 'light'>(((localStorage.getItem(THEME_KEY) as 'dark' | 'light') || 'dark'))

const ACCENT_HEX: Record<AccentColor, string> = {
  blue:   '#3b82f6',
  violet: '#8b5cf6',
  emerald:'#10b981',
  rose:   '#f43f5e',
  amber:  '#f59e0b',
  cyan:   '#06b6d4',
  pink:   '#ec4899',
}

export function applyAccent(c: AccentColor) {
  const hex = ACCENT_HEX[c]
  document.documentElement.style.setProperty('--accent', hex)
  document.documentElement.style.setProperty('--accent-hover', hex + 'cc')
  document.documentElement.style.setProperty('--accent-pressed', hex + '99')
  accentColor.value = c
  try { localStorage.setItem(ACCENT_KEY, c) } catch {}
}

export function setTheme(t: 'dark' | 'light') {
  themeMode.value = t
  document.documentElement.dataset.theme = t
  try { localStorage.setItem(THEME_KEY, t) } catch {}
}

watch(accentColor, (v) => applyAccent(v), { immediate: true })
watch(themeMode, (v) => setTheme(v), { immediate: true })

export const ACCENT_PALETTE = Object.entries(ACCENT_HEX).map(([k, hex]) => ({
  key: k,
  hex,
  label: ({ blue: '蓝', violet: '紫', emerald: '绿', rose: '玫红', amber: '琥珀', cyan: '青', pink: '粉' } as Record<string, string>)[k] || k,
}))
