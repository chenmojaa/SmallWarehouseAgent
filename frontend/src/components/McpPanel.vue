<script setup lang='ts'>
import { computed, onMounted, reactive, ref } from 'vue'
import { t } from '@/i18n'
import { useRouter } from 'vue-router'
import { useMessage, NAlert, NButton, NEmpty, NInput, NModal, NPopconfirm, NSpin, NSwitch, NTag } from 'naive-ui'
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
const router = useRouter()
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

const tab = ref<'presets' | 'servers'>('presets')
const quickPrompt = ref('')
function pickTab(name: 'presets' | 'servers') { tab.value = name }
const suggestedPrompts = ['列出桌面上的 .txt 文件', '查询仓库里本周增加的 star', '记住我喜欢 7 点吃早饭、开会议选 14:00']

const enabledCount = computed(() => servers.value.filter((s) => s.enabled).length)
const installedIds = computed(() => new Set(servers.value.map((s) => s.id)))
const readyCount = computed(() => enabledCount.value + (presets.value?.length || 0))

function isReadyToDemo() {
  return enabledCount.value > 0 || installedIds.value.size > 0 || servers.value.length > 0
}

async function quickStart() {
  const q = quickPrompt.value.trim()
  if (!q) return
  if (!isReadyToDemo()) { message.warning('请先启用一个 MCP 再试试：从预设库一键安装'); return }
  // 暂存问题并跳转聊天页，由 ChatView 挂载后自动发送
  sessionStorage.setItem('mcp-quick-prompt', q)
  quickPrompt.value = ''
  router.push('/chat')
}

function resetForm() {
  editingId.value = ''
  Object.assign(form, { name: '', transport: 'stdio', command: '', args: [], env: {}, url: '', description: '', enabled: true })
  argsText.value = '[]'
  envText.value = '{}'
}

function openCreate() { resetForm(); editorOpen.value = true }

function openEdit(server: MCPServer) {
  editingId.value = server.id
  Object.assign(form, { name: server.name, transport: server.transport, command: server.command, args: [...server.args], env: { ...server.env }, url: server.url, description: server.description, enabled: server.enabled })
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
    errorMessage.value = String((error as Error)?.message || error || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadData())

function parseJson(value: string, label: string): unknown {
  try { return JSON.parse(value) } catch { throw new Error(label + ' JSON 格式不正确') }
}

async function saveServer() {
  if (!form.name.trim()) { message.warning('请先填写 MCP 名称'); return }
  const parsedArgs = parseJson(argsText.value, '启动参数')
  const parsedEnv = parseJson(envText.value, '环境变量')
  if (!Array.isArray(parsedArgs) || parsedArgs.some((item) => typeof item !== 'string')) { message.warning('启动参数必须是字符串数组'); return }
  if (!parsedEnv || typeof parsedEnv !== 'object' || Array.isArray(parsedEnv)) { message.warning('环境变量必须是对象'); return }
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
    if (editingId.value) { await updateMcpServer(editingId.value, payload); message.success('MCP 配置已更新') }
    else { await createMcpServer(payload); message.success('MCP 已添加') }
    editorOpen.value = false
    await loadData()
  } catch (error) {
    message.error(String((error as Error)?.message || error || '保存失败'))
  } finally {
    saving.value = false
  }
}

async function installPreset(preset: MCPPreset) {
  try {
    const result = await installMcpPreset(preset.id)
    const msg = result.created ? ('已添加 ' + preset.name) : (preset.name + ' 已在列表中')
    message[result.created ? 'success' : 'info'](msg)
    await loadData()
  } catch (error) { message.error(String((error as Error)?.message || error || '安装失败')) }
}

async function toggleServer(server: MCPServer, enabled: boolean) {
  try { await updateMcpServer(server.id, { enabled }); server.enabled = enabled; message.info(enabled ? '已启用 MCP' : '已停用 MCP') }
  catch (error) { message.error(String((error as Error)?.message || error || '更新失败')) }
}

async function testServer(server: MCPServer) {
  testingId.value = server.id
  try { const result = await testMcpServer(server.id); message[result.ok ? 'success' : 'warning'](result.message); await loadData() }
  catch (error) { message.error(String((error as Error)?.message || error || '测试失败')) }
  finally { testingId.value = '' }
}

async function removeServer(server: MCPServer) {
  try { await deleteMcpServer(server.id); message.info('MCP 已删除'); await loadData() }
  catch (error) { message.error(String((error as Error)?.message || error || '删除失败')) }
}

function formatTime(value?: string | null) {
  if (!value) return '从未更新'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// 暴露给父页面（顶部统计）
defineExpose({ summary: computed(() => ({ enabled: enabledCount.value, servers: servers.value.length, presets: presets.value.length })) })
</script>

<template>
  <div class='mcp-panel'>
    <n-spin :show='loading'>
      <!-- 快捷体验条 -->
      <div class='quick-bar'>
        <div class='quick-stats'>
          <button class='qstat' @click='pickTab("presets")'>
            <strong>{{ presets.length }}</strong><span>{{ t('mcp.tab.presets', '预设', 'Presets') }}</span>
          </button>
          <button class='qstat' :class='{ on: enabledCount > 0 }' @click='pickTab("servers")'>
            <strong>{{ enabledCount }}</strong><span>{{ t('mcp.preset.enabled', '已启用', 'Enabled') }}</span>
          </button>
          <button class='qstat' @click='pickTab("servers")'>
            <strong>{{ servers.length }}</strong><span>{{ t('ui.misc.026', '总服务', '总服务') }}</span>
          </button>
        </div>
        <div class='quick-input-row'>
          <n-input v-model:value='quickPrompt' placeholder='试试问：“查询仓库本周增加的 star” — 需先启用 MCP' size='small' round @keyup.enter='quickStart'>
            <template #prefix><span class='quick-emoji'>✨</span></template>
          </n-input>
          <n-button type='primary' size='small' round @click='quickStart'>{{ t('ui.misc.016', '发起试试', '发起试试') }}</n-button>
          <n-button size='small' round quaternary @click='openCreate'><span style='font-weight:600'>+</span>{{ t('ui.skills.001', '&nbsp;添加 MCP', '&nbsp;添加 MCP') }}</n-button>
        </div>
        <div class='quick-chips'>
          <button v-for='(p, i) in suggestedPrompts' :key='i' class='chip' @click='quickPrompt = p'>{{ p }}</button>
          <span class='ready-pill'><span class='ready-dot'></span>{{ readyCount }} 个资源在线</span>
        </div>
      </div>

      <n-alert v-if='errorMessage' class='mcp-alert' type='error' :show-icon='false'>
        {{ errorMessage }}
      </n-alert>

      <!-- 子 tab -->
      <div class='sub-tabs'>
        <button class='sub-tab' :class='{ active: tab === "presets" }' @click='pickTab("presets")'>{{ t('ui.misc.056', '预设库', '预设库') }}</button>
        <button class='sub-tab' :class='{ active: tab === "servers" }' @click='pickTab("servers")'>{{ t('ui.misc.029', '我的服务', '我的服务') }}</button>
      </div>

      <!-- 预设库 -->
      <div v-if='tab === "presets"' class='pane'>
        <div class='section-heading'>
          <div>
            <h2>{{ t('ui.misc.032', '推荐预设', '推荐预设') }}</h2>
            <p>{{ t('ui.models.002', '一键加入。加入后会被模型自动发现，随时可调用。', '一键加入。加入后会被模型自动发现，随时可调用。') }}</p>
          </div>
          <span class='section-meta'>{{ presets.length }} 项</span>
        </div>
        <div v-if='!presets.length' class='empty-block'>
          <n-empty description='暂无可用预设' />
        </div>
        <div v-else class='preset-grid'>
          <article v-for='preset in presets' :key='preset.id' class='preset-card' :class='{ installed: installedIds.has(preset.id) }' @click='installPreset(preset)'>
            <div class='preset-top'>
              <div class='preset-emoji' :data-cat='preset.category || "agent"'>{{ preset.emoji || '✦' }}</div>
              <n-tag v-if='installedIds.has(preset.id)' size='tiny' type='success' round class='installed-tag'>{{ t('ui.misc.021', '已添加', '已添加') }}</n-tag>
              <n-tag v-else-if='preset.category' size='tiny' round class='cat-tag'>{{ preset.category }}</n-tag>
            </div>
            <h3>{{ preset.name_zh || preset.name }}<span v-if='preset.name_zh' class='dot'>·</span><span v-if='preset.name_zh' class='en'>{{ preset.name }}</span></h3>
            <p>{{ preset.description }}</p>
            <code class='preset-cmd'>{{ preset.command }} {{ (preset.args || []).join(' ') }}</code>
            <div class='preset-footer'>
              <small v-if='preset.requirements'>需要：{{ preset.requirements }}</small>
              <small v-else>&nbsp;</small>
              <span class='install-pill' :class='{ on: !installedIds.has(preset.id) }'>
                {{ installedIds.has(preset.id) ? '已安装' : '一键启用 →' }}
              </span>
            </div>
          </article>
        </div>
      </div>

      <!-- 我的服务 -->
      <div v-else class='pane'>
        <div class='section-heading'>
          <div>
            <h2>{{ t('ui.skills.004', '已配置的 MCP', '已配置的 MCP') }}</h2>
            <p>{{ t('ui.models.004', '点击「测试」可立即校验连通性，验证后会被模型自动调用。', '点击「测试」可立即校验连通性，验证后会被模型自动调用。') }}</p>
          </div>
          <span class='section-meta'>{{ servers.length }} 个已配置</span>
        </div>
        <div v-if='!servers.length' class='empty-block large'>
          <div class='empty-icon'>✦</div>
          <h3>{{ t('ui.skills.013', '还没有 MCP 服务', '还没有 MCP 服务') }}</h3>
          <p>{{ t('ui.misc.008', '从预设库一键安装，或者手动添加。', '从预设库一键安装，或者手动添加。') }}</p>
          <n-button type='primary' round @click='openCreate'>{{ t('ui.misc.030', '手动添加', '手动添加') }}</n-button>
        </div>
        <div v-else class='server-list'>
          <article v-for='server in servers' :key='server.id' class='server-card' :class='{ off: !server.enabled }'>
            <div class='server-bar' :class='server.transport'>
              <span class='server-bar-icon'>{{ server.transport === 'http' ? '⇄' : '$_' }}</span>
            </div>
            <div class='server-main'>
              <div class='server-title'>
                <strong>{{ server.name }}</strong>
                <n-tag size='tiny' round :type='server.enabled ? "success" : "default"'>{{ server.enabled ? '启用' : '停用' }}</n-tag>
                <n-tag size='tiny' round>{{ server.transport }}</n-tag>
              </div>
              <p v-if='server.description' class='server-desc'>{{ server.description }}</p>
              <code class='server-config'>{{ server.command }} {{ (server.args || []).join(' ') }}</code>
              <div class='server-meta'><span>更新于 {{ formatTime(server.updated_at) }}</span></div>
            </div>
            <div class='server-actions'>
              <n-switch :value='server.enabled' size='small' @update:value='(v) => toggleServer(server, v)' @click.stop />
              <n-button size='small' quaternary :loading='testingId === server.id' @click.stop='testServer(server)'>测试</n-button>
              <n-button size='small' quaternary @click.stop='openEdit(server)'>编辑</n-button>
              <n-popconfirm positive-text="确认" negative-text="取消" @positive-click='removeServer(server)'>                <template #trigger>
                  <n-button size='small' quaternary type='error' @click.stop>{{ t('chat.msg.delete', '删除', 'Delete') }}</n-button>
                </template>
                确定删除「{{ server.name }}」？
              </n-popconfirm>
            </div>
          </article>
        </div>
      </div>
    </n-spin>

    <n-modal v-model:show='editorOpen' preset='card' :title='editingId ? "编辑 MCP" : "添加 MCP"' class='mcp-editor' :bordered='false' size='huge'>
      <div class='editor-body'>
        <!-- Section 1: Basic Info -->
        <section class='editor-section'>
          <div class='section-header'>
            <span class='section-icon'>📋</span>
            <h4>{{ t('ui.misc.019', '基本信息', '基本信息') }}</h4>
          </div>
          <div class='field-group'>
            <div class='field'>
              <label class='field-label'>{{ t('ui.misc.036', '服务名称', '服务名称') }}</label>
              <n-input v-model:value='form.name' placeholder='例如：本地文件助手' class='editor-input' />
            </div>
            <div class='field'>
              <label class='field-label'>{{ t('ui.misc.047', '用途说明', '用途说明') }}<span class='optional'>{{ t('ui.misc.061', '（可选）', '（可选）') }}</span></label>
              <n-input v-model:value='form.description' type='textarea' :autosize='{ minRows: 2, maxRows: 3 }' placeholder='简要描述这个 MCP 的用途' class='editor-input' />
            </div>
          </div>
        </section>

        <!-- Section 2: Transport -->
        <section class='editor-section'>
          <div class='section-header'>
            <span class='section-icon'>🔌</span>
            <h4>{{ t('mcp.add.transport', '传输方式', 'Transport') }}</h4>
          </div>
          <div class='transport-toggle'>
            <button class='transport-btn' :class='{ active: form.transport === "stdio" }' type='button' @click='form.transport = "stdio"'>
              <span class='transport-icon'>⌨️</span>
              <span class='transport-name'>stdio</span>
              <span class='transport-desc'>{{ t('ui.misc.018', '命令行', '命令行') }}</span>
            </button>
            <button class='transport-btn' :class='{ active: form.transport === "http" }' type='button' @click='form.transport = "http"'>
              <span class='transport-icon'>🌐</span>
              <span class='transport-name'>http</span>
              <span class='transport-desc'>SSE / Streamable</span>
            </button>
          </div>
          <div class='field'>
            <label v-if='form.transport === "stdio"' class='field-label'>{{ t('mcp.add.command', '启动命令', 'Command') }}</label>
            <label v-else class='field-label'>{{ t('mcp.add.url', '服务地址', 'URL') }}</label>
            <n-input v-if='form.transport === "stdio"' v-model:value='form.command' placeholder='例如：npx / uvx / python' class='editor-input' />
            <n-input v-else v-model:value='form.url' placeholder='http://127.0.0.1:3000/mcp' class='editor-input' />
          </div>
        </section>

        <!-- Section 3: Args & Env -->
        <section class='editor-section'>
          <div class='section-header'>
            <span class='section-icon'>⚙️</span>
            <h4>{{ t('ui.misc.058', '高级配置', '高级配置') }}</h4>
          </div>
          <div class='field-group'>
            <div class='field'>
              <label class='field-label'>{{ t('ui.misc.017', '启动参数', '启动参数') }}<span class='optional'>{{ t('ui.misc.060', '（JSON 数组）', '（JSON 数组）') }}</span></label>
              <n-input v-if='form.transport === "stdio"' v-model:value='argsText' type='textarea' :autosize='{ minRows: 2, maxRows: 5 }' placeholder='["-y", "@modelcontextprotocol/server-filesystem"]' class='editor-input mono' />
              <div v-else class='field-hint-box'>
                <span class='field-hint-icon'>💡</span>
                <span>{{ t('ui.misc.002', 'HTTP 模式无需启动参数', 'HTTP 模式无需启动参数') }}</span>
              </div>
            </div>
            <div class='field'>
              <label class='field-label'>{{ t('mcp.add.env', '环境变量', 'Environment') }}<span class='optional'>{{ t('ui.misc.059', '（JSON 对象）', '（JSON 对象）') }}</span></label>
              <n-input v-model:value='envText' type='textarea' :autosize='{ minRows: 2, maxRows: 5 }' placeholder='{"API_KEY": "sk-xxx"}' class='editor-input mono' />
            </div>
          </div>
        </section>
      </div>
      <template #footer>
        <div class='editor-footer'>
          <n-button quaternary @click='editorOpen = false'>{{ t('chat.perm.confirm.cancel', '取消', 'Cancel') }}</n-button>
          <n-button type='primary' :loading='saving' @click='saveServer'>
            {{ editingId ? '更新配置' : '添加服务' }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.mcp-panel { padding: 16px 28px 48px; }
.quick-bar {
  padding: 18px 20px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(99, 102, 241, .10), rgba(56, 189, 248, .05) 55%, rgba(255, 255, 255, 0)), var(--bg-elevated);
  box-shadow: 0 10px 30px rgba(15, 23, 42, .08);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.quick-stats { display: flex; gap: 10px; }
.qstat {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 16px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: rgba(255, 255, 255, .03);
  cursor: pointer;
  transition: all .18s ease;
}
.qstat:hover { border-color: rgba(99, 102, 241, .5); background: rgba(99, 102, 241, .08); }
.qstat.on { border-color: rgba(34, 197, 94, .55); background: rgba(34, 197, 94, .08); }
.qstat strong { font-size: 18px; font-weight: 800; background-image: linear-gradient(135deg, #818cf8, #38bdf8); -webkit-background-clip: text; background-clip: text; color: transparent; }
.qstat span { font-size: 12px; color: var(--text-muted); }
.quick-input-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 10px; align-items: center; }
.quick-emoji { font-size: 14px; }
.quick-chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.chip { border: 1px solid var(--border-soft); background: rgba(255, 255, 255, .04); color: var(--text-secondary); padding: 5px 10px; border-radius: 999px; font-size: 11px; cursor: pointer; transition: all .15s ease; }
.chip:hover { border-color: rgba(99, 102, 241, .5); color: var(--text-primary); background: rgba(99, 102, 241, .1); }
.ready-pill { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; font-size: 11px; color: var(--text-muted); }
.ready-dot { width: 7px; height: 7px; border-radius: 50%; background: #4ade80; box-shadow: 0 0 8px #4ade80; }
.mcp-alert { margin: 14px 0; }
.sub-tabs { display: inline-flex; gap: 4px; padding: 4px; border-radius: 10px; background: var(--hover-bg); margin: 16px 0 4px; }
.sub-tab { height: 30px; min-width: 88px; border: 0; border-radius: 7px; background: transparent; color: var(--text-secondary); cursor: pointer; font-size: 13px; }
.sub-tab.active { color: var(--text-primary); font-weight: 600; background: var(--bg-elevated); box-shadow: 0 1px 4px rgba(15, 23, 42, .08); }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin: 18px 0 14px; }
.section-heading h2 { margin: 0; font-size: 15px; color: var(--text-primary); font-weight: 600; }
.section-heading p { margin: 4px 0 0; color: var(--text-muted); font-size: 12px; line-height: 1.55; }
.section-meta { font-size: 11px; color: var(--text-muted); padding: 4px 10px; border: 1px solid var(--border-soft); border-radius: 999px; background: var(--bg-elevated); white-space: nowrap; }
.preset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.preset-card { position: relative; display: flex; flex-direction: column; padding: 18px 18px 16px; border: 1px solid var(--border-soft); border-radius: 16px; background: var(--bg-elevated); cursor: pointer; transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.preset-card:hover { transform: translateY(-2px); border-color: rgba(99, 102, 241, .55); box-shadow: 0 14px 32px rgba(15, 23, 42, .10); }
.preset-card.installed { border-color: rgba(34, 197, 94, .35); }
.preset-top { display: flex; align-items: center; justify-content: space-between; }
.preset-emoji { width: 44px; height: 44px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; font-size: 22px; background: linear-gradient(135deg, rgba(99, 102, 241, .18), rgba(56, 189, 248, .12)); }
.preset-emoji[data-cat='internet'] { background: linear-gradient(135deg, rgba(56, 189, 248, .22), rgba(14, 165, 233, .12)); }
.preset-emoji[data-cat='dev']      { background: linear-gradient(135deg, rgba(168, 85, 247, .22), rgba(99, 102, 241, .12)); }
.preset-emoji[data-cat='agent']    { background: linear-gradient(135deg, rgba(99, 102, 241, .22), rgba(56, 189, 248, .12)); }
.preset-emoji[data-cat='local']    { background: linear-gradient(135deg, rgba(34, 197, 94, .22), rgba(16, 185, 129, .12)); }
.preset-emoji[data-cat='data']     { background: linear-gradient(135deg, rgba(244, 114, 182, .22), rgba(225, 29, 72, .10)); }
.preset-card h3 { margin: 12px 0 4px; font-size: 15px; color: var(--text-primary); font-weight: 600; display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.preset-card h3 .dot { color: var(--text-muted); }
.preset-card h3 .en  { color: var(--text-muted); font-size: 11px; font-weight: 400; }
.preset-card p { min-height: 50px; margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.preset-cmd { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 7px 9px; border-radius: 8px; background: var(--hover-bg); color: var(--text-secondary); font-size: 11px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.preset-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; gap: 8px; }
.preset-footer small { color: var(--text-muted); font-size: 11px; }
.install-pill { font-size: 11px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border-soft); color: var(--text-secondary); background: transparent; transition: all .15s ease; }
.install-pill.on { background: linear-gradient(135deg, rgba(99, 102, 241, .95), rgba(56, 189, 248, .85)); border-color: transparent; color: #fff; box-shadow: 0 4px 14px rgba(99, 102, 241, .35); }
.preset-card.installed .install-pill { color: var(--text-muted); }
.empty-block { border: 1px dashed var(--border-soft); border-radius: 16px; padding: 36px 18px; text-align: center; background: var(--bg-elevated); }
.empty-block.large { padding: 64px 24px; background: radial-gradient(420px 220px at 50% 0%, rgba(99, 102, 241, .08), transparent 70%), var(--bg-elevated); }
.empty-block.large .empty-icon { width: 64px; height: 64px; margin: 0 auto 14px; border-radius: 18px; display: inline-flex; align-items: center; justify-content: center; font-size: 28px; color: #6366f1; background: linear-gradient(135deg, rgba(99, 102, 241, .18), rgba(56, 189, 248, .12)); }
.empty-block.large h3 { margin: 0 0 6px; color: var(--text-primary); font-weight: 600; }
.empty-block.large p  { margin: 0 0 18px; color: var(--text-muted); font-size: 12px; }
.server-list { display: flex; flex-direction: column; gap: 12px; }
.server-card { display: grid; grid-template-columns: 56px minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 16px 18px; border: 1px solid var(--border-soft); border-radius: 16px; background: var(--bg-elevated); transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.server-card:hover { transform: translateY(-1px); border-color: rgba(99, 102, 241, .45); box-shadow: 0 10px 24px rgba(15, 23, 42, .07); }
.server-card.off { opacity: .7; }
.server-bar { height: 56px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 14px; background: linear-gradient(135deg, #6366f1, #38bdf8); }
.server-bar.http { background: linear-gradient(135deg, #f59e0b, #ef4444); }
.server-bar-icon { font-family: ui-monospace, monospace; letter-spacing: -.5px; }
.server-main { min-width: 0; }
.server-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.server-title strong { font-size: 14px; color: var(--text-primary); font-weight: 600; }
.server-desc { margin: 6px 0 8px; color: var(--text-secondary); font-size: 12px; line-height: 1.5; }
.server-config { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 7px 9px; border-radius: 8px; background: var(--hover-bg); color: var(--text-secondary); font-size: 11px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; margin-bottom: 8px; }
.server-meta { color: var(--text-muted); font-size: 11px; }
.server-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.mcp-editor { width: min(720px, calc(100vw - 32px)); }
.mcp-editor :deep(.n-card-header) { padding-bottom: 4px; }
.mcp-editor :deep(.n-card-header__main) { font-size: 18px; font-weight: 700; letter-spacing: -0.02em; }
.editor-body { display: flex; flex-direction: column; gap: 20px; }
.editor-section { padding: 16px 18px; border-radius: 14px; border: 1px solid var(--border-soft); background: var(--bg-elevated); }
.section-header { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.section-header h4 { margin: 0; font-size: 14px; font-weight: 600; color: var(--text-primary); }
.section-icon { font-size: 16px; }
.field-group { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--text-secondary); letter-spacing: 0.02em; }
.field-label .optional { font-weight: 400; color: var(--text-muted); }
.editor-input :deep(.n-input) { border-radius: 10px; }
.editor-input :deep(.n-input .n-input__border),
.editor-input :deep(.n-input .n-input__state-border) { border-radius: 10px; }
.editor-input.mono :deep(textarea) { font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size: 13px; }
.field-hint-box { display: flex; align-items: center; gap: 6px; padding: 10px 12px; border-radius: 10px; background: var(--hover-bg); color: var(--text-muted); font-size: 13px; }
.field-hint-icon { font-size: 14px; }
.transport-toggle { display: flex; gap: 10px; margin-bottom: 14px; }
.transport-btn { flex: 1; display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 10px; border: 1.5px solid var(--border-soft); background: var(--bg-app); cursor: pointer; transition: all 0.2s; }
.transport-btn:hover { border-color: var(--brand-blue); background: var(--hover-bg); }
.transport-btn.active { border-color: var(--brand-blue); background: rgba(59, 130, 246, 0.08); }
.transport-icon { font-size: 18px; }
.transport-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.transport-desc { font-size: 11px; color: var(--text-muted); margin-left: auto; }
.editor-footer { display: flex; justify-content: flex-end; gap: 10px; }
.editor-footer :deep(.n-button) { border-radius: 10px; }
@media (max-width: 720px) {
  .quick-input-row { grid-template-columns: 1fr; }
  .preset-grid { grid-template-columns: 1fr; }
}

.mcp-title { font-size: 22px; font-weight: 700; margin: 0 0 6px; background: linear-gradient(135deg, var(--accent, #3b82f6), #ec4899); -webkit-background-clip: text; background-clip: text; color: transparent; }
.mcp-sub { font-size: 13px; opacity: 0.65; margin: 0; max-width: 640px; }
.mcp-quick { display: flex; gap: 8px; align-items: center; }
.quick-input { background: var(--bg-soft, rgba(255,255,255,0.04)); border: 1px solid var(--border-soft); color: var(--text-primary); padding: 8px 12px; border-radius: 8px; min-width: 280px; font-size: 13px; }
.quick-btn { background: var(--accent, #3b82f6); color: #fff; border: 0; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; }
.quick-btn:hover { filter: brightness(1.1); }
.hero { display: none !important; }
</style>
