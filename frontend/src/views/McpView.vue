<script setup lang='ts'>
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage, NAlert, NButton, NCard, NEmpty, NInput, NModal, NPopconfirm, NSelect, NSpace, NSpin, NSwitch, NTag } from 'naive-ui'
import {
  createMcpServer,
  deleteMcpServer,
  installMcpPreset,
  listMcpPresets,
  listMcpServers,
  testMcpServer,
  updateMcpServer,
  type MCPPreset,
  type MCPServer,
  type MCPServerPayload,
} from '@/api/mcp'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const testingId = ref('')
const errorMessage = ref('')
const servers = ref<MCPServer[]>([])
const presets = ref<MCPPreset[]>([])
const editorOpen = ref(false)
const editingId = ref('')
const argsText = ref('[]')
const envText = ref('{}')

const form = reactive<MCPServerPayload>({
  name: '',
  transport: 'stdio',
  command: '',
  args: [],
  env: {},
  url: '',
  description: '',
  enabled: true,
})

const transportOptions = [
  { label: 'stdio（命令行）', value: 'stdio' },
  { label: 'http（SSE / Streamable HTTP）', value: 'http' },
]

const serverCountLabel = computed(() => `${servers.value.length} 个已配置`)

function resetForm() {
  editingId.value = ''
  Object.assign(form, {
    name: '',
    transport: 'stdio',
    command: '',
    args: [],
    env: {},
    url: '',
    description: '',
    enabled: true,
  })
  argsText.value = '[]'
  envText.value = '{}'
}

function openCreate() {
  resetForm()
  editorOpen.value = true
}

function openEdit(server: MCPServer) {
  editingId.value = server.id
  Object.assign(form, {
    name: server.name,
    transport: server.transport,
    command: server.command,
    args: [...server.args],
    env: { ...server.env },
    url: server.url,
    description: server.description,
    enabled: server.enabled,
  })
  argsText.value = JSON.stringify(server.args, null, 2)
  envText.value = JSON.stringify(server.env, null, 2)
  editorOpen.value = true
}

async function loadData() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [serverResult, presetResult] = await Promise.all([listMcpServers(), listMcpPresets()])
    servers.value = serverResult.items
    presets.value = presetResult.items
  } catch (error) {
    errorMessage.value = (error as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadData())

function parseJson(value: string, label: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    throw new Error(`${label} JSON 格式不正确`)
  }
}

async function saveServer() {
  if (!form.name.trim()) {
    message.warning('请先填写 MCP 名称')
    return
  }
  const parsedArgs = parseJson(argsText.value, '启动参数')
  const parsedEnv = parseJson(envText.value, '环境变量')
  if (!Array.isArray(parsedArgs) || parsedArgs.some((item) => typeof item !== 'string')) {
    message.warning('启动参数必须是字符串数组')
    return
  }
  if (!parsedEnv || typeof parsedEnv !== 'object' || Array.isArray(parsedEnv)) {
    message.warning('环境变量必须是对象')
    return
  }
  saving.value = true
  try {
    const payload: MCPServerPayload = {
      ...form,
      name: form.name.trim(),
      args: parsedArgs as string[],
      env: parsedEnv as Record<string, string>,
      url: form.url.trim(),
      description: form.description.trim(),
    }
    if (editingId.value) {
      await updateMcpServer(editingId.value, payload)
      message.success('MCP 配置已更新')
    } else {
      await createMcpServer(payload)
      message.success('MCP 已添加')
    }
    editorOpen.value = false
    await loadData()
  } catch (error) {
    message.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

async function installPreset(preset: MCPPreset) {
  try {
    const result = await installMcpPreset(preset.id)
    message[result.created ? 'success' : 'info'](result.created ? `已添加 ${preset.name}` : `${preset.name} 已在列表中`)
    await loadData()
  } catch (error) {
    message.error((error as Error).message)
  }
}

async function toggleServer(server: MCPServer, enabled: boolean) {
  try {
    await updateMcpServer(server.id, { enabled })
    server.enabled = enabled
    message.info(enabled ? '已启用 MCP' : '已停用 MCP')
  } catch (error) {
    message.error((error as Error).message)
  }
}

async function testServer(server: MCPServer) {
  testingId.value = server.id
  try {
    const result = await testMcpServer(server.id)
    message[result.ok ? 'success' : 'warning'](result.message)
    await loadData()
  } catch (error) {
    message.error((error as Error).message)
  } finally {
    testingId.value = ''
  }
}

async function removeServer(server: MCPServer) {
  try {
    await deleteMcpServer(server.id)
    message.info('MCP 已删除')
    await loadData()
  } catch (error) {
    message.error((error as Error).message)
  }
}

function statusType(server: MCPServer) {
  if (server.last_test_ok === true) return 'success'
  if (server.last_test_ok === false) return 'error'
  return 'default'
}

function statusText(server: MCPServer) {
  if (server.last_test_ok === true) return '已验证'
  if (server.last_test_ok === false) return '需检查'
  return '未测试'
}

function formatDate(value: string | null) {
  if (!value) return '尚未测试'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class='mcp-page'>
    <div class='mcp-header'>
      <div>
        <h1>MCP</h1>
        <p>管理 Model Context Protocol 工具，让 Agent 获得文件、网页、记忆和开发能力。</p>
      </div>
      <n-button type='primary' @click='openCreate'>+ 添加 MCP</n-button>
    </div>

    <n-alert v-if='errorMessage' type='error' class='mcp-alert' :show-icon='true'>
      {{ errorMessage }}
    </n-alert>

    <n-spin :show='loading'>
      <section class='mcp-section'>
        <div class='section-heading'>
          <div>
            <h2>预设 MCP</h2>
            <p>从常用服务开始，添加后可以继续调整启动参数和权限。</p>
          </div>
          <n-tag size='small' :bordered='false'>{{ serverCountLabel }}</n-tag>
        </div>
        <div class='preset-grid'>
          <n-card v-for='preset in presets' :key='preset.id' :bordered='false' class='preset-card'>
            <div class='preset-top'>
              <span class='preset-emoji'>{{ preset.emoji }}</span>
              <n-tag size='tiny' :bordered='false' type='info'>{{ preset.category }}</n-tag>
            </div>
            <h3>{{ preset.name_zh }} <span>{{ preset.name }}</span></h3>
            <p>{{ preset.description }}</p>
            <code>{{ preset.command }} {{ preset.args.join(' ') }}</code>
            <div class='preset-footer'>
              <small>{{ preset.requirements }}</small>
              <n-button
                size='tiny'
                round
                :type='preset.installed ? `default` : `primary`'
                :disabled='preset.installed'
                @click='installPreset(preset)'
              >
                {{ preset.installed ? '已添加' : '添加' }}
              </n-button>
            </div>
          </n-card>
        </div>
      </section>

      <section class='mcp-section'>
        <div class='section-heading'>
          <div>
            <h2>已配置</h2>
            <p>已添加的服务器可以编辑、测试、启停或删除。测试当前只检查启动器和 URL 配置。</p>
          </div>
        </div>
        <n-empty v-if='!loading && servers.length === 0' description='还没有配置 MCP，先从上方预设添加一个' />
        <div v-else class='server-list'>
          <n-card v-for='server in servers' :key='server.id' :bordered='false' class='server-card'>
            <div class='server-row'>
              <div class='server-main'>
                <div class='server-title'>
                  <strong>{{ server.name }}</strong>
                  <n-tag size='tiny' :bordered='false' :type='server.enabled ? `success` : `default`'>
                    {{ server.enabled ? '已启用' : '已停用' }}
                  </n-tag>
                  <n-tag size='tiny' :bordered='false' :type='statusType(server)'>
                    {{ statusText(server) }}
                  </n-tag>
                </div>
                <p v-if='server.description'>{{ server.description }}</p>
                <div class='server-config'>
                  <code v-if='server.transport === `stdio`'>{{ server.command }} {{ server.args.join(' ') }}</code>
                  <code v-else>{{ server.url }}</code>
                </div>
                <small>{{ server.last_test_message }} · {{ formatDate(server.last_test_at) }}</small>
              </div>
              <div class='server-actions'>
                <n-switch :value='server.enabled' @update:value='enabled => toggleServer(server, enabled)' />
                <n-button size='tiny' quaternary @click='openEdit(server)'>编辑</n-button>
                <n-button size='tiny' quaternary :loading='testingId === server.id' @click='testServer(server)'>测试</n-button>
                <n-popconfirm @positive-click='removeServer(server)'>
                  <template #trigger>
                    <n-button size='tiny' quaternary type='error'>删除</n-button>
                  </template>
                  删除这个 MCP 配置？
                </n-popconfirm>
              </div>
            </div>
          </n-card>
        </div>
      </section>
    </n-spin>

    <n-modal v-model:show='editorOpen' preset='card' :title='editingId ? `编辑 MCP` : `添加 MCP`' class='mcp-editor'>
      <n-space vertical :size='12'>
        <n-input v-model:value='form.name' placeholder='名称，例如：我的 GitHub' />
        <n-input v-model:value='form.description' placeholder='用途说明（可选）' />
        <n-select v-model:value='form.transport' :options='transportOptions' />
        <n-input v-if='form.transport === `stdio`' v-model:value='form.command' placeholder='启动命令，例如 npx' />
        <n-input v-if='form.transport === `http`' v-model:value='form.url' placeholder='http://127.0.0.1:3000/mcp' />
        <n-input
          v-if='form.transport === `stdio`'
          v-model:value='argsText'
          type='textarea'
          :autosize='{ minRows: 3, maxRows: 8 }'
          placeholder='启动参数，JSON 字符串数组'
        />
        <n-input
          v-model:value='envText'
          type='textarea'
          :autosize='{ minRows: 3, maxRows: 8 }'
          placeholder='环境变量，JSON 对象，例如 {TOKEN: "}'
        />
        <n-space justify='end'>
          <n-button quaternary @click='editorOpen = false'>取消</n-button>
          <n-button type='primary' :loading='saving' @click='saveServer'>保存</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </div>
</template>

<style scoped>
.mcp-page {
  height: 100%;
  overflow-y: auto;
  padding: 24px 28px 40px;
  box-sizing: border-box;
}
.mcp-header,
.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
.mcp-header { margin-bottom: 22px; }
.mcp-header h1,
.section-heading h2 {
  margin: 0;
  color: var(--text-primary);
}
.mcp-header h1 { font-size: 24px; }
.mcp-header p,
.section-heading p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}
.mcp-alert { margin-bottom: 14px; }
.mcp-section { margin-top: 22px; }
.section-heading { align-items: center; margin-bottom: 12px; }
.section-heading h2 { font-size: 16px; }
.preset-grid,
.server-list { display: grid; gap: 12px; }
.preset-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.preset-card,
.server-card {
  border: 1px solid var(--border-soft);
  background: var(--bg-elevated);
}
.preset-card :deep(.n-card__content) { padding: 15px; }
.preset-top,
.preset-footer,
.server-row,
.server-title,
.server-actions { display: flex; align-items: center; }
.preset-top,
.preset-footer,
.server-row { justify-content: space-between; gap: 10px; }
.preset-emoji {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: rgba(59, 130, 246, .1);
  font-size: 20px;
}
.preset-card h3 { margin: 12px 0 5px; color: var(--text-primary); font-size: 15px; }
.preset-card h3 span { color: var(--text-muted); font-size: 11px; font-weight: 400; }
.preset-card p {
  min-height: 54px;
  margin: 0 0 10px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}
.preset-card code,
.server-config code {
  display: block;
  overflow: hidden;
  padding: 7px 8px;
  border-radius: 7px;
  background: var(--hover-bg);
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preset-footer { margin-top: 12px; }
.preset-footer small { color: var(--text-muted); font-size: 10px; }
.server-list { grid-template-columns: 1fr; }
.server-card :deep(.n-card__content) { padding: 14px 15px; }
.server-row { align-items: flex-start; }
.server-main { min-width: 0; flex: 1; }
.server-title { gap: 7px; flex-wrap: wrap; }
.server-title strong { color: var(--text-primary); font-size: 14px; }
.server-main p { margin: 5px 0 8px; color: var(--text-secondary); font-size: 12px; }
.server-config { max-width: 760px; margin-bottom: 7px; }
.server-main small { color: var(--text-muted); font-size: 11px; }
.server-actions { flex-shrink: 0; gap: 5px; flex-wrap: wrap; justify-content: flex-end; }
.mcp-editor { width: min(620px, calc(100vw - 32px)); }
@media (max-width: 900px) {
  .preset-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .server-row { flex-direction: column; }
  .server-actions { justify-content: flex-start; }
}
@media (max-width: 560px) {
  .mcp-page { padding: 18px 14px 30px; }
  .mcp-header { flex-direction: column; }
  .preset-grid { grid-template-columns: 1fr; }
}
</style>
