<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage, NCard, NSpace, NButton, NInput, NSelect, NTag, NEmpty, NSpin, NPopconfirm, NCode, NText } from 'naive-ui'
import { get, postJson, patchJson, deleteReq } from '@/api/client'
import { _t } from '@/i18n'

const message = useMessage()
const t = _t

// ===== Project rules (AGENTS.md) ============================================
const rulesText = ref('')
const rulesChars = ref(0)
const rulesLoading = ref(false)
const rulesSaving = ref(false)
const rulesDirty = ref(false)

async function loadRules() {
  rulesLoading.value = true
  try {
    const r = await get<{ exists: boolean; chars: number; content: string }>('/project-rules')
    rulesText.value = r.content || ''
    rulesChars.value = r.chars
    rulesDirty.value = false
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    rulesLoading.value = false
  }
}

async function saveRules() {
  rulesSaving.value = true
  try {
    const r = await postJson<{ ok: boolean; chars: number; path: string }>('/project-rules', { content: rulesText.value })
    message.success(t('operations.rules.saved', `\u5df2\u4fdd\u5b58 AGENTS.md (${r.chars} \u5b57\u7b26)`, `AGENTS.md saved (${r.chars} chars)`))
    rulesChars.value = r.chars
    rulesDirty.value = false
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    rulesSaving.value = false
  }
}

// ===== Hooks ===============================================================
interface HookSpec { name: string; phase: 'PreToolUse' | 'PostToolUse'; tool: string; script: string; timeout_s: number; enabled: boolean }
interface HookRun { name: string; phase: string; decision: string; reason: string; duration_ms: number; error: string }
const hooks = ref<HookSpec[]>([])
const hookRuns = ref<HookRun[]>([])
const hooksLoading = ref(false)

async function loadHooks() {
  hooksLoading.value = true
  try {
    const r = await get<{ specs: HookSpec[]; recent: HookRun[] }>('/hooks')
    hooks.value = r.specs || []
    hookRuns.value = r.recent || []
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    hooksLoading.value = false
  }
}

async function runHookTest() {
  try {
    const r = await postJson<{ results: any[]; blocked: boolean; reason: string }>('/hooks/test', {
      phase: 'PreToolUse',
      event: { tool: 'mcp:fs:fs_write', arguments: { path: 'C:/Windows/System32/test.txt' } },
    })
    if (r.blocked) message.warning(t('operations.hooks.test_blocked', `\u88ab\u62e6\u622a\uff1a${r.reason}`, `Blocked: ${r.reason}`))
    else message.success(t('operations.hooks.test_passed', `\u6d4b\u8bd5\u901a\u8fc7\uff08${r.results.length} \u4e2a hook\uff09`, `Test passed (${r.results.length} hooks)`))
  } catch (e) {
    message.error((e as Error).message)
  }
}

// ===== Permissions ========================================================
interface PermRow { tool: string; decision: string; source: string }
const perms = ref<PermRow[]>([])
const permsLoading = ref(false)
const decisions = [
  { label: t('operations.permissions.allow', '\u5141\u8bb8', 'Allow'), value: 'allow' },
  { label: t('operations.permissions.deny', '\u62d2\u7edd', 'Deny'), value: 'deny' },
  { label: t('operations.permissions.ask', '\u9700\u6388\u6743', 'Ask'), value: 'ask' },
  { label: t('operations.permissions.inherit', '\u9ed8\u8ba4', 'Default'), value: 'inherit' },
]

async function loadPerms() {
  permsLoading.value = true
  try {
    const r = await get<{ items: PermRow[] }>('/permissions/rules')
    perms.value = r.items
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    permsLoading.value = false
  }
}

async function setPerm(tool: string, decision: string) {
  try {
    await patchJson('/permissions/rules', { tool, decision })
    await loadPerms()
    message.success(t('operations.permissions.set', `\u5df2\u4fee\u6539 ${tool}`, `Updated ${tool}`))
  } catch (e) {
    message.error((e as Error).message)
  }
}

// ===== Background =========================================================
const reindexLog = ref<string[]>([])
const reindexRunning = ref(false)
const reindexDone = ref(false)

async function startReindex() {
  reindexLog.value = []
  reindexRunning.value = true
  reindexDone.value = false
  try {
    const res = await fetch('/api/background/reindex', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Auth-Token': localStorage.getItem('hd_auth_token') || '' },
      body: '{}',
    })
    if (!res.body) throw new Error('no body')
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const raw of lines) {
        if (raw.startsWith('data:')) {
          const payload = raw.slice(5).trim()
          if (!payload) continue
          try { reindexLog.value.push(JSON.stringify(JSON.parse(payload))) } catch { reindexLog.value.push(payload) }
        }
      }
    }
    reindexDone.value = true
    message.success(t('operations.bg.done', '\u91cd\u5efa\u5b8c\u6210', 'Reindex finished'))
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    reindexRunning.value = false
  }
}

onMounted(() => {
  loadRules()
  loadHooks()
  loadPerms()
})
</script>

<template>
  <div class="operations-root">
    <n-space vertical size="large">
      <!-- Project Rules (AGENTS.md) -->
      <n-card :title="t('operations.rules.title', 'AGENTS.md \u9879\u76ee\u89c4\u5219', 'AGENTS.md Project Rules')" size="small">
        <template #header-extra>
          <n-tag v-if="rulesDirty" type="warning" size="small">{{ t('operations.dirty', '\u672a\u4fdd\u5b58', 'unsaved') }}</n-tag>
          <n-tag v-else type="success" size="small">{{ t('operations.saved', '\u5df2\u540c\u6b65', 'synced') }}</n-tag>
        </template>
        <n-spin :show="rulesLoading">
          <n-input
            type="textarea"
            v-model:value="rulesText"
            :placeholder="t('operations.rules.placeholder', '\u8f93\u5165 AGENTS.md \u5185\u5bb9\u2026', 'Type AGENTS.md content\u2026')"
            :autosize="{ minRows: 6, maxRows: 14 }"
            style="font-family: ui-monospace, monospace"
            @update:value="rulesDirty = true"
          />
        </n-spin>
        <n-space justify="space-between" align="center" style="margin-top: 10px">
          <n-text depth="3" style="font-size: 12px">
            {{ rulesChars }} {{ t('operations.chars', '\u5b57\u7b80', 'chars') }}
          </n-text>
          <n-space size="small">
            <n-button size="small" @click="loadRules">{{ t('common.reload', '\u5237\u65b0', 'Reload') }}</n-button>
            <n-button size="small" type="primary" :disabled="!rulesDirty" :loading="rulesSaving" @click="saveRules">
              {{ t('common.save', '\u4fdd\u5b58', 'Save') }}
            </n-button>
          </n-space>
        </n-space>
      </n-card>

      <!-- Hooks -->
      <n-card :title="t('operations.hooks.title', 'Hooks\uff08\u547d\u4ee4\u8c03\u7528\u4e8b\u4ef6\u94a9\u5b50\uff09', 'Hooks (tool lifecycle)')" size="small">
        <template #header-extra>
          <n-button size="small" @click="runHookTest" :disabled="hooks.length === 0">{{ t('operations.hooks.test', '\u6d4b\u8bd5', 'Test') }}</n-button>
        </template>
        <n-spin :show="hooksLoading">
          <n-empty v-if="hooks.length === 0" description="No hooks registered" size="small" />
          <div v-else class="hooks-list">
            <div v-for="h in hooks" :key="h.name" class="hook-row">
              <n-tag :type="h.phase === 'PreToolUse' ? 'warning' : 'info'" size="small">{{ h.phase }}</n-tag>
              <n-text strong style="margin-left: 8px">{{ h.name }}</n-text>
              <n-text depth="3" style="margin-left: 8px; font-size: 12px">{{ h.tool }}</n-text>
              <n-text depth="3" style="margin-left: 8px; font-size: 12px; flex: 1; word-break: break-all">{{ h.script }}</n-text>
              <n-tag :type="h.enabled ? 'success' : 'default'" size="small">{{ h.enabled ? 'ON' : 'OFF' }}</n-tag>
            </div>
          </div>
        </n-spin>
      </n-card>

      <!-- Permissions -->
      <n-card :title="t('operations.permissions.title', '\u5de5\u5177\u8c03\u7528\u6743\u9650', 'Tool Permissions')" size="small">
        <n-spin :show="permsLoading">
          <n-empty v-if="perms.length === 0" description="No rules" size="small" />
          <div v-else class="perm-list">
            <div v-for="row in perms" :key="row.tool" class="perm-row">
              <n-text :type="row.source === 'user' ? 'warning' : 'default'">{{ row.tool }}</n-text>
              <n-select
                :value="row.decision"
                :options="decisions"
                style="width: 120px; margin-left: auto"
                @update:value="(v: string) => setPerm(row.tool, v)"
              />
              <n-tag size="small" style="margin-left: 8px">{{ row.source }}</n-tag>
            </div>
          </div>
        </n-spin>
      </n-card>

      <!-- Background Reindex -->
      <n-card :title="t('operations.bg.title', '\u540e\u53f0\u4efb\u52a1', 'Background Tasks')" size="small">
        <n-space>
          <n-button :loading="reindexRunning" :disabled="reindexRunning" @click="startReindex">
            {{ t('operations.bg.reindex', '\u91cd\u5efa\u77e5\u8bc6\u5e93\u7d22\u5f15', 'Reindex knowledge base') }}
          </n-button>
          <n-text v-if="reindexDone && !reindexRunning" type="success">{{ t('operations.bg.last_done', '\u4e0a\u6b21\u4efb\u52a1\u5b8c\u6210', 'last task finished') }}</n-text>
        </n-space>
        <div v-if="reindexLog.length > 0" class="bg-log">
          <div v-for="(line, i) in reindexLog" :key="i" class="bg-log-line">{{ line }}</div>
        </div>
      </n-card>
    </n-space>
  </div>
</template>

<style scoped>
.operations-root { padding: 4px 0; }
.hook-row, .perm-row {
  display: flex;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px dashed rgba(127, 127, 127, 0.15);
  font-size: 13px;
}
.hook-row:last-child, .perm-row:last-child { border-bottom: 0; }
.bg-log {
  margin-top: 12px;
  max-height: 240px;
  overflow-y: auto;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: rgba(127, 127, 127, 0.06);
  padding: 8px 10px;
  border-radius: 4px;
}
.bg-log-line {
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 0;
}
</style>
