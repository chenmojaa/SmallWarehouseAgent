<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Marked, type Tokens } from 'marked'
import DOMPurify from 'dompurify'
import mermaid from 'mermaid'
import type { Citation } from '@/api/chat'

const props = defineProps<{
  role: 'user' | 'assistant' | 'system'
  content: string
  citations?: Citation[]
  activeIndex?: number | null
}>()

const emit = defineEmits<{
  'update:activeIndex': [number]
}>()

const bubbleEl = ref<HTMLElement | null>(null)
const detailsRef = ref<HTMLDetailsElement | null>(null)

// Per-bubble thinking-process open/close state is stored in localStorage
// keyed by a hash of the think content. This survives route navigation
// (which unmounts <ChatView> and remounts every <MessageBubble>) so the
// user's manual expand/collapse choice persists across pages.
const THINK_KEY_PREFIX = 'hd:thinkOpen:'
function hashContent(s: string): string {
  let h = 5381 >>> 0
  for (let i = 0; i < s.length; i++) {
    h = (((h << 5) + h) ^ s.charCodeAt(i)) >>> 0
  }
  return h.toString(36)
}

let thinkToggleHandler: ((e: Event) => void) | null = null
async function syncThinkOpenState(): Promise<void> {
  const el = detailsRef.value
  const t = think.value
  // Detach any handler attached to a previous <details> element so we
  // never leak listeners when Vue swaps the node on content update.
  if (el && thinkToggleHandler) {
    el.removeEventListener('toggle', thinkToggleHandler)
    thinkToggleHandler = null
  }
  if (!el || !t) return
  const key = THINK_KEY_PREFIX + hashContent(t)
  // Only override the element's open state when we have an explicit saved
  // choice. A missing key means "user hasn't decided yet", so we leave the
  // element's default in place (the <details> ships with the `open` attr so
  // the thinking content is visible on first render).
  const saved = localStorage.getItem(key)
  if (saved !== null && el.open !== (saved === '1')) {
    el.open = saved === '1'
  }
  thinkToggleHandler = () => {
    localStorage.setItem(key, el.open ? '1' : '0')
  }
  el.addEventListener('toggle', thinkToggleHandler)
}


// 1) Pull the LEADING <think>...</think> block off and keep it as a separate
//    piece, so the template can render it as a collapsible "thinking
//    process" section above the actual answer. Inline (non-leading)
//    <think> blocks are still stripped from the main body to keep the rest
//    of the pipeline unchanged.
function splitThink(s: string): { think: string; rest: string } {
  const m = s.match(/^\s*<think>([\s\S]*?)<\/think>([\s\S]*)$/i)
  if (m) {
    return { think: m[1].trim(), rest: m[2] }
  }
  const cleaned = s.replace(/<think>[\s\S]*?(<\/think>|$)/gi, '').trim()
  return { think: '', rest: cleaned }
}

// 2) Pull a trailing "来源：[n][m]..." line off the end. Keep the indices as
//    clickable buttons; the body itself never carries [n] markers.
const SOURCE_LINE_RE = /\n?\s*\u6765\u6e90\s*[:\uff1a]\s*((?:\[\s*\d+\s*\])+)\s*$/
function splitSourceLine(s: string): { body: string; tokens: number[] } {
  const m = s.match(SOURCE_LINE_RE)
  if (!m) return { body: s, tokens: [] }
  const tokens = Array.from(m[1].matchAll(/\[(\d+)\]/g)).map(x => parseInt(x[1], 10))
  return { body: s.slice(0, m.index).trimEnd(), tokens }
}

const thinkRest = computed(() => splitThink(props.content || ''))
const think = computed(() => thinkRest.value.think)
const cleaned = computed(() => thinkRest.value.rest)
const sourceLine = computed(() => splitSourceLine(cleaned.value))
const body = computed(() => sourceLine.value.body)
const sourceTokens = computed(() => sourceLine.value.tokens)

// Only show source tokens that have a matching citation in props.citations.
// Guards against two failure modes: (1) LLM hallucinating [N] with no
// retrieved chunks (citations = []) and (2) LLM citing an index out of
// range. Either way, dangling [N] buttons render as broken UI.
const validSourceTokens = computed<number[]>(() => {
  const cites = props.citations
  if (!cites || cites.length === 0) return []
  const max = cites.length
  return sourceTokens.value.filter(n => n >= 1 && n <= max)
})

// 3) Replace inline [n] markers with clickable citation buttons so the
//    user can tap them directly in the answer text (instead of having
//    them silently stripped). The buttons share the same toggle() handler
//    as the footer source-line buttons.
function replaceCiteMarkers(s: string): string {
  return s.replace(/\[\s*(\d+)\s*\]/g, (_m, nStr: string) => {
    const n = parseInt(nStr, 10)
    const cites = props.citations
    if (!cites || cites.length === 0) return ''
    if (n < 1 || n > cites.length) return ''
    return `<span class="cite-inline" data-cite="${n}" title="查看来源 [${n}]">[${n}]</span>`
  })
}
const bodyNoCite = computed(() => replaceCiteMarkers(body.value))

// 4) Markdown -> HTML via marked, with a custom renderer for ```mermaid blocks.
function escapeHtml(s: string): string {
  return s.replace(/[&<>"'\u00b7]/g, (c) => {
    switch (c) {
      case '&': return '&amp;'
      case '<': return '&lt;'
      case '>': return '&gt;'
      case '"': return '&quot;'
      case "'": return '&#39;'
      default: return c
    }
  })
}

const md = new Marked({
  gfm: true,
  breaks: true,
})

md.use({
  renderer: {
    code(token: Tokens.Code): string {
      const lang = (token.lang || '').trim()
      const text = token.text
      if (lang === 'mermaid') {
        // Keep raw source in data-source so we can re-render after mount.
        return '<div class="mermaid-block" data-source="' +
          encodeURIComponent(text) + '">' + escapeHtml(text) + '</div>'
      }
      const langClass = lang ? ' class="language-' + escapeHtml(lang) + '"' : ''
      return '<pre><code' + langClass + '>' + escapeHtml(text) + '</code></pre>'
    },
  },
})

const renderedHtml = computed(() => {
  if (props.role !== 'assistant') return ''
  const raw = md.parse(bodyNoCite.value, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['data-source', 'data-rendered', 'class', 'data-cite', 'title'],
    ADD_TAGS: ['span'],
  })
})

// 事件委托：点击内联 [n] 引用按钮时高亮对应来源
let mdBodyClickHandler: ((e: MouseEvent) => void) | null = null
function bindMdBodyClick(): void {
  const el = bubbleEl.value
  if (!el) return
  if (mdBodyClickHandler) el.removeEventListener('click', mdBodyClickHandler)
  mdBodyClickHandler = (e: MouseEvent) => {
    const target = (e.target as HTMLElement).closest('.cite-inline') as HTMLElement | null
    if (!target) return
    const n = parseInt(target.getAttribute('data-cite') || '', 10)
    if (!isNaN(n)) toggle(n)
  }
  el.addEventListener('click', mdBodyClickHandler)
}

function toggle(n: number): void {
  if (props.activeIndex === n) emit('update:activeIndex', -1)
  else emit('update:activeIndex', n)
}

// 5) Mermaid rendering on mount + on every content change.
let mermaidReady = false
async function ensureMermaid(): Promise<void> {
  if (mermaidReady) return
  mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose', fontFamily: 'inherit' })
  mermaidReady = true
}

async function renderMermaidIn(root: HTMLElement): Promise<void> {
  const blocks = Array.from(root.querySelectorAll<HTMLElement>('.mermaid-block:not([data-rendered])'))
  for (const block of blocks) {
    const source = decodeURIComponent(block.getAttribute('data-source') || block.textContent || '')
    const id = 'mmd-' + Math.random().toString(36).slice(2, 10)
    try {
      const { svg } = await mermaid.render(id, source)
      block.innerHTML = svg
      block.setAttribute('data-rendered', '1')
    } catch (e) {
      // Fall back to a plain code block so the raw source is still visible.
      block.classList.remove('mermaid-block')
      block.innerHTML = '<pre><code class="language-mermaid">' + escapeHtml(source) + '</code></pre>'
      block.setAttribute('data-rendered', '1')
    }
  }
}

async function refreshMermaid(): Promise<void> {
  await ensureMermaid()
  await nextTick()
  if (bubbleEl.value) await renderMermaidIn(bubbleEl.value)
}

onMounted(() => {
  refreshMermaid()
  bindMdBodyClick()
})
watch(renderedHtml, () => {
  refreshMermaid()
  bindMdBodyClick()
})
// Restore + persist thinking open/close. flush:'post' ensures detailsRef is
// populated (the v-if element exists) by the time we read it.
watch([think, detailsRef], () => {
  syncThinkOpenState().catch(() => { /* localStorage may be blocked */ })
}, { flush: 'post', immediate: true })
onBeforeUnmount(() => {
  if (detailsRef.value && thinkToggleHandler) {
    detailsRef.value.removeEventListener('toggle', thinkToggleHandler)
    thinkToggleHandler = null
  }
})
</script>

<template>
  <div :class="['bubble-row', role]">
    <div :class="['bubble', role]">
      <details v-if="role === 'assistant' && think" ref="detailsRef" class="think-section">
        <summary>思考过程</summary>
        <div class="think-body">{{ think }}</div>
      </details>
      <div v-if="role === 'assistant'" ref="bubbleEl" class="md-body" v-html="renderedHtml"></div>
      <div v-else class="plain-body">{{ bodyNoCite }}</div>
      <div v-if="role === 'assistant' && validSourceTokens.length" class="source-line">
        <span>\u6765\u6e90\uff1a</span>
        <button
          v-for="n in validSourceTokens"
          :key="n"
          class="cite-btn"
          :class="{ active: activeIndex === n }"
          type="button"
          @click.stop="toggle(n)"
        >[{{ n }}]</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bubble-row {
  display: flex;
  margin-bottom: 12px;
}
.bubble-row.user { justify-content: flex-end; }
.bubble-row.assistant { justify-content: flex-start; }

.bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 10px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}
.bubble.user {
  background: var(--bg-bubble-user);
  color: var(--text-on-user);
}
.bubble.assistant {
  background: var(--bg-bubble-assistant);
  color: var(--text-primary);
}
.bubble.system {
  background: var(--bg-bubble-thinking);
  color: var(--text-muted);
  font-style: italic;
}

/* Markdown body (assistant only) lives inside a div that opts out of pre-wrap
   so marked's own <p>/<pre>/<ul> whitespace is respected. */
.md-body {
  white-space: normal;
}
.md-body :deep(p) { margin: 0.5em 0; }
.md-body :deep(p:first-child) { margin-top: 0; }
.md-body :deep(p:last-child) { margin-bottom: 0; }
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) { margin: 0.8em 0 0.4em; font-weight: 600; line-height: 1.3; }
.md-body :deep(h1) { font-size: 1.4em; }
.md-body :deep(h2) { font-size: 1.25em; }
.md-body :deep(h3) { font-size: 1.1em; }
.md-body :deep(h4) { font-size: 1em; }
.md-body :deep(ul),
.md-body :deep(ol) { margin: 0.5em 0; padding-left: 1.5em; }
.md-body :deep(li) { margin: 0.2em 0; }
.md-body :deep(li > p) { margin: 0.1em 0; }
.md-body :deep(strong) { font-weight: 600; }
.md-body :deep(em) { font-style: italic; }
.md-body :deep(del) { color: var(--text-muted, #888); }
.md-body :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 5px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
}
.md-body :deep(pre) {
  background: rgba(0, 0, 0, 0.04);
  padding: 10px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.6em 0;
  white-space: pre;
}
.md-body :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 0.85em;
}
.md-body :deep(a) {
  color: var(--accent, #3b82f6);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.md-body :deep(blockquote) {
  border-left: 3px solid var(--border-soft, #ddd);
  padding: 0 12px;
  margin: 0.6em 0;
  color: var(--text-muted, #666);
}
.md-body :deep(table) {
  border-collapse: collapse;
  margin: 0.6em 0;
}
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid var(--border-soft, #ddd);
  padding: 4px 8px;
}
.md-body :deep(th) { background: rgba(0, 0, 0, 0.03); }
.md-body :deep(hr) {
  border: none;
  border-top: 1px dashed var(--border-soft, #ddd);
  margin: 0.8em 0;
}
.md-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 0.4em 0;
}
.md-body :deep(.mermaid-block) {
  text-align: center;
  margin: 12px 0;
  padding: 12px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 8px;
  overflow-x: auto;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.85em;
}
.md-body :deep(.mermaid-block[data-rendered]) {
  background: transparent;
  padding: 0;
  white-space: normal;
}
.md-body :deep(.mermaid-block[data-rendered] svg) {
  max-width: 100%;
  height: auto;
}

.think-section {
  margin: -2px 0 8px;
  padding: 6px 10px;
  border: 1px dashed var(--border-soft, #ddd);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.03);
  font-size: 12px;
  opacity: 0.85;
}
.think-section > summary {
  cursor: pointer;
  user-select: none;
  color: var(--text-muted, #888);
  font-weight: 500;
}
.think-section > summary::marker { color: var(--text-muted, #888); }
.think-body {
  margin-top: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-muted, #666);
  line-height: 1.55;
}

.source-line {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-soft, #ddd);
  font-size: 13px;
}
.source-line span {
  color: var(--text-muted, #888);
  margin-right: 4px;
}

.cite-btn {
  display: inline;
  padding: 0 4px;
  margin: 0 1px;
  border: none;
  background: transparent;
  color: var(--accent, #3b82f6);
  font: inherit;
  cursor: pointer;
  border-radius: 4px;
  text-decoration: underline;
  text-underline-offset: 2px;
  line-height: inherit;
}
.cite-btn:hover { background: rgba(59, 130, 246, 0.12); }
.cite-btn.active {
  background: var(--accent, #3b82f6);
  color: #fff;
  text-decoration: none;
}

/* 内联引用 [n] 标记：正文中直接显示的小圆角徽章 */
.cite-inline {
  display: inline-block;
  padding: 0 5px;
  margin: 0 1px;
  font-size: 0.85em;
  font-weight: 600;
  line-height: 1.5;
  color: var(--accent, #3b82f6);
  background: rgba(59, 130, 246, 0.10);
  border-radius: 4px;
  cursor: pointer;
  vertical-align: baseline;
  user-select: none;
  transition: background 0.15s, color 0.15s;
}
.cite-inline:hover {
  background: rgba(59, 130, 246, 0.22);
}
.cite-inline.active {
  background: var(--accent, #3b82f6);
  color: #fff;
}
</style>
