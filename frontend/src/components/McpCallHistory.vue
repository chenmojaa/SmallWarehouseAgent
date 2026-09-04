<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { t } from '@/i18n'
import { useMessage } from 'naive-ui'

interface Call {
  id: number
  session_id: string | null
  server_id: string
  tool_name: string
  arguments: any
  status: string
  latency_ms: number
  result_preview: string | null
  error_message: string | null
  created_at: string | null
}

const message = useMessage()
const calls = ref<Call[]>([])
const stats = ref<any>(null)
const loading = ref(false)
const filterStatus = ref<string | null>(null)
const filterServer = ref<string | null>(null)

const filtered = computed(() => {
  return calls.value.filter((c: any) => {
    if (filterStatus.value && c.status !== filterStatus.value) return false
    if (filterServer.value && c.server_id !== filterServer.value) return false
    return true
  })
})

async function load() {
  loading.value = true
  try {
    const token = localStorage.getItem('hd_auth_token') || ''
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['X-Auth-Token'] = token
    const [c, s] = await Promise.all([
      fetch('/api/mcp/calls?limit=200', { headers }).then(r => r.json()),
      fetch('/api/mcp/calls/stats', { headers }).then(r => r.json()),
    ])
    calls.value = c.calls || []
    stats.value = s
  } catch (e: any) {
    message.error('加载失败：' + (e?.message || String(e)))
  } finally {
    loading.value = false
  }
}

async function clear() {
  if (!confirm('确认清空所有调用历史？')) return
  try {
    const token = localStorage.getItem('hd_auth_token') || ''
    await fetch('/api/mcp/calls', { method: 'DELETE', headers: { 'X-Auth-Token': token } })
    calls.value = []
    message.success('已清空')
    await load()
  } catch (e: any) {
    message.error('清空失败：' + (e?.message || String(e)))
  }
}

function fmtTime(s: string | null) {
  if (!s) return ''
  try { return new Date(s).toLocaleString('zh-CN') } catch { return s }
}

function statusColor(s: string) {
  return ({ ok: '#10b981', error: '#ef4444', timeout: '#f59e0b', denied: '#6b7280' } as Record<string,string>)[s] || '#6b7280'
}

onMounted(load)
</script>

<template>
  <div class="mcp-history">
    <div class="hist-stats" v-if="stats">
      <div class="stat-card"><span class="stat-num">{{ stats.total }}</span><span class="stat-label">{{ t('ui.misc.027', '总调用', '总调用') }}</span></div>
      <div class="stat-card"><span class="stat-num" :style="{ color: statusColor('ok') }">{{ stats.by_status['ok'] || 0 }}</span><span class="stat-label">{{ t('ui.misc.028', '成功', '成功') }}</span></div>
      <div class="stat-card"><span class="stat-num" :style="{ color: statusColor('error') }">{{ stats.by_status['error'] || 0 }}</span><span class="stat-label">{{ t('chat.tool.status.failed', '失败', 'failed') }}</span></div>
      <div class="stat-card"><span class="stat-num">{{ stats.avg_latency_ms }}ms</span><span class="stat-label">{{ t('ui.misc.022', '平均延迟', '平均延迟') }}</span></div>
      <div class="stat-card"><span class="stat-num">{{ stats.p95_latency_ms }}ms</span><span class="stat-label">P95</span></div>
    </div>
    <div class="hist-toolbar">
      <select v-model="filterStatus" class="hist-select">
        <option :value="null">{{ t('ui.misc.010', '全部状态', '全部状态') }}</option>
        <option value="ok">{{ t('ui.misc.028', '成功', '成功') }}</option>
        <option value="error">{{ t('chat.tool.status.failed', '失败', 'failed') }}</option>
        <option value="timeout">{{ t('ui.misc.052', '超时', '超时') }}</option>
        <option value="denied">{{ t('chat.perm.dialog.deny', '拒绝', 'Deny') }}</option>
      </select>
      <select v-model="filterServer" class="hist-select">
        <option :value="null">{{ t('ui.misc.009', '全部服务', '全部服务') }}</option>
        <option v-for="s in Object.keys(stats?.by_server || {})" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="hist-btn" @click="load">{{ t('ui.misc.063', '🔄 刷新', '🔄 刷新') }}</button>
      <button class="hist-btn danger" @click="clear">{{ t('ui.misc.064', '🗑 清空', '🗑 清空') }}</button>
    </div>
    <div v-if="loading" class="hist-empty">{{ t('common.loading', '加载中…', 'Loading…') }}</div>
    <div v-else-if="filtered.length === 0" class="hist-empty">{{ t('mcp.history.empty', '暂无调用记录', 'No calls yet') }}</div>
    <div v-else class="hist-list">
      <details v-for="c in filtered.slice(0, 100)" :key="c.id" class="hist-item">
        <summary>
          <span class="hist-dot" :style="{ background: statusColor(c.status) }"></span>
          <span class="hist-server">{{ c.server_id }}</span>
          <span class="hist-tool">.{{ c.tool_name }}</span>
          <span class="hist-latency">{{ c.latency_ms }}ms</span>
          <span class="hist-time">{{ fmtTime(c.created_at) }}</span>
        </summary>
        <div class="hist-body">
          <div v-if="c.arguments" class="hist-block">
            <div class="hist-label">{{ t('chat.perm.dialog.args', '参数', 'Arguments') }}</div>
            <pre>{{ JSON.stringify(c.arguments, null, 2) }}</pre>
          </div>
          <div v-if="c.result_preview" class="hist-block">
            <div class="hist-label">{{ t('ui.misc.048', '结果预览', '结果预览') }}</div>
            <pre>{{ c.result_preview }}</pre>
          </div>
          <div v-if="c.error_message" class="hist-block error">
            <div class="hist-label">{{ t('ui.misc.055', '错误', '错误') }}</div>
            <pre>{{ c.error_message }}</pre>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<style scoped>
.mcp-history { display: flex; flex-direction: column; height: 100%; gap: 12px; padding: 16px; overflow: hidden; }
.hist-stats { display: flex; gap: 10px; flex-wrap: wrap; }
.stat-card { background: var(--bg-soft, rgba(255,255,255,0.04)); border: 1px solid var(--border-soft, rgba(255,255,255,0.08)); border-radius: 8px; padding: 12px 16px; min-width: 100px; display: flex; flex-direction: column; }
.stat-num { font-size: 22px; font-weight: 600; }
.stat-label { font-size: 11px; color: var(--text-muted, #888); margin-top: 2px; }
.hist-toolbar { display: flex; gap: 8px; align-items: center; }
.hist-select { background: var(--bg-soft); border: 1px solid var(--border-soft); color: var(--text-primary); padding: 6px 10px; border-radius: 6px; font-size: 13px; }
.hist-btn { padding: 6px 12px; border: 1px solid var(--border-soft); background: transparent; color: var(--text-primary); border-radius: 6px; cursor: pointer; font-size: 13px; }
.hist-btn:hover { background: var(--hover-bg); }
.hist-btn.danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.hist-empty { text-align: center; padding: 40px; color: var(--text-muted, #888); }
.hist-list { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; flex: 1; }
.hist-item { background: var(--bg-soft, rgba(255,255,255,0.03)); border: 1px solid var(--border-soft); border-radius: 6px; overflow: hidden; }
.hist-item summary { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; list-style: none; font-size: 13px; }
.hist-item summary::-webkit-details-marker { display: none; }
.hist-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.hist-server { font-weight: 600; }
.hist-tool { opacity: 0.7; }
.hist-latency { margin-left: auto; opacity: 0.6; font-size: 11px; font-family: monospace; }
.hist-time { opacity: 0.5; font-size: 11px; }
.hist-body { padding: 8px 12px 12px; border-top: 1px solid var(--border-soft); }
.hist-block { margin-top: 6px; }
.hist-label { font-size: 11px; color: var(--text-muted, #888); margin-bottom: 4px; }
.hist-block pre { font-size: 12px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; margin: 0; max-height: 200px; overflow: auto; white-space: pre-wrap; }
.hist-block.error pre { color: #fca5a5; }
</style>
