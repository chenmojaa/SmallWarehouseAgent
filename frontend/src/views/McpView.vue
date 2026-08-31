<script setup lang='ts'>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useMessage, NAlert, NButton, NEmpty, NInput, NModal, NPopconfirm, NSelect, NSpace, NSpin, NSwitch, NTag, NTabs, NTabPane } from 'naive-ui'
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

const serverCountLabel = computed(() => servers.value.length + ' 个已配置')

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
    errorMessage.value = (error && (error as Error).message) || String(error) || '加载失败'
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
    message.error((error && (error as Error).message) || String(error) || '保存失败')
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
  } catch (error) { message.error((error && (error as Error).message) || String(error) || '安装失败') }
}

async function toggleServer(server: MCPServer, enabled: boolean) {
  try { await updateMcpServer(server.id, { enabled }); server.enabled = enabled; message.info(enabled ? '已启用 MCP' : '已停用 MCP') }
  catch (error) { message.error((error && (error as Error).message) || String(error) || '更新失败') }
}

async function testServer(server: MCPServer) {
  testingId.value = server.id
  try { const result = await testMcpServer(server.id); message[result.ok ? 'success' : 'warning'](result.message); await loadData() }
  catch (error) { message.error((error && (error as Error).message) || String(error) || '测试失败') }
  finally { testingId.value = '' }
}

async function removeServer(server: MCPServer) {
  try { await deleteMcpServer(server.id); message.info('MCP 已删除'); await loadData() }
  catch (error) { message.error((error && (error as Error).message) || String(error) || '删除失败') }
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

const enabledCount = computed(() => servers.value.filter((s) => s.enabled).length)
const installedIds = computed(() => new Set(servers.value.map((s) => s.id)))

function formatTime(value?: string | null) {
  if (!value) return '从未更新'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const tab = ref<'presets' | 'servers'>('presets')
const quickPrompt = ref('')
function pickTab(name: 'presets' | 'servers') { tab.value = name }
function isReadyToDemo() {
  return enabledCount.value > 0 || installedIds.value.size > 0 || servers.value.length > 0
}
const suggestedPrompts = ['列出桌面上的 .txt 文件', '查询仓库里本周增加的 star', '记住我喜欢 7 点吃早饭、开会议选 14:00']

async function quickStart() {
  const q = quickPrompt.value.trim()
  if (!q) return
  if (!isReadyToDemo()) { message.warning('请先启用一个 MCP 再试试：从预设库一键安装'); return }
  message.info('正在跳转聊天并启动伪发送...')
  window.dispatchEvent(new CustomEvent('mcp-quick-prompt', { detail: q }))
  quickPrompt.value = ''
}

// ============= Particle background (cleanup hoisted to top-level) =============
const canvasRef = ref<HTMLCanvasElement | null>(null)
let particlesRunning = false
let particlesRaf = 0
let particlesRO: ResizeObserver | null = null
function stopParticles() {
  if (particlesRaf) cancelAnimationFrame(particlesRaf)
  particlesRaf = 0
  if (particlesRO) { particlesRO.disconnect(); particlesRO = null }
  particlesRunning = false
}
function startParticles() {
  const cv = canvasRef.value
  if (!cv || particlesRunning) return
  particlesRunning = true
  const ctx = cv.getContext('2d')
  if (!ctx) { stopParticles(); return }
  const dpr = Math.max(1, window.devicePixelRatio || 1)
  const resize = () => {
    if (!cv) return
    const r = cv.getBoundingClientRect()
    cv.width = r.width * dpr
    cv.height = r.height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
  resize()
  particlesRO = new ResizeObserver(resize)
  particlesRO.observe(cv)
  type P = { x: number; y: number; vx: number; vy: number; r: number; a: number; hue: number }
  const rand = (lo: number, hi: number) => lo + Math.random() * (hi - lo)
  const N = 56
  const ps: P[] = Array.from({ length: N }, () => ({ x: rand(0, cv.width / dpr), y: rand(0, cv.height / dpr), vx: rand(-0.22, 0.22), vy: rand(-0.22, 0.22), r: rand(0.8, 2.0), a: rand(0.35, 0.9), hue: rand(220, 280) }))
  let mouseX = -9999, mouseY = -9999
  const onMove = (e: PointerEvent) => { const r = cv.getBoundingClientRect(); mouseX = e.clientX - r.left; mouseY = e.clientY - r.top }
  const onLeave = () => { mouseX = -9999; mouseY = -9999 }
  cv.addEventListener('pointermove', onMove)
  cv.addEventListener('pointerleave', onLeave)
  const step = () => {
    if (!cv) return
    const w = cv.width / dpr, h = cv.height / dpr
    ctx.clearRect(0, 0, w, h)
    for (const p of ps) {
      const dx = mouseX - p.x, dy = mouseY - p.y
      const d2 = dx * dx + dy * dy
      if (d2 < 140 * 140) { const f = (1 - d2 / (140 * 140)) * 0.05; p.vx += dx * f * 0.02; p.vy += dy * f * 0.02 }
      p.vx *= 0.985; p.vy *= 0.985
      const sp = Math.hypot(p.vx, p.vy)
      if (sp > 0.6) { p.vx *= 0.6 / sp; p.vy *= 0.6 / sp }
      p.x += p.vx; p.y += p.vy
      if (p.x < -10) p.x = w + 10
      if (p.x > w + 10) p.x = -10
      if (p.y < -10) p.y = h + 10
      if (p.y > h + 10) p.y = -10
    }
    for (let i = 0; i < ps.length; i++) {
      for (let j = i + 1; j < ps.length; j++) {
        const a = ps[i], b = ps[j]
        const dx = a.x - b.x, dy = a.y - b.y
        const d2 = dx * dx + dy * dy
        if (d2 < 110 * 110) {
          const alpha = (1 - d2 / (110 * 110)) * 0.45
          ctx.strokeStyle = 'hsla(' + (a.hue + b.hue) / 2 + ', 90%, 72%, ' + alpha + ')'
          ctx.lineWidth = 0.8
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.lineTo(b.x, b.y)
          ctx.stroke()
        }
      }
    }
    for (const p of ps) {
      ctx.beginPath()
      ctx.fillStyle = 'hsla(' + p.hue + ', 95%, 72%, ' + p.a + ')'
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fill()
    }
    particlesRaf = requestAnimationFrame(step)
  }
  particlesRaf = requestAnimationFrame(step)
}

onMounted(() => { startParticles() })
onBeforeUnmount(() => { stopParticles() })

const readyCount = computed(() => enabledCount.value + (presets.value?.length || 0))

</script>

<template>
  <div class='mcp-page'>
    <n-spin :show='loading'>
      <section class='hero'>
        <canvas ref='canvasRef' class='hero-particles'></canvas>
        <div class='hero-glow'></div>
        <div class='hero-grid'></div>
        <div class='hero-inner'>
          <div class='hero-top'>
            <div class='hero-badge'>
              <span class='badge-dot'></span>
              <span class='badge-text'>MCP 控制中心</span>
            </div>
            <div class='hero-status'>
              <span class='status-pill ok'><span class='status-dot'></span>系统就绪</span>
              <span class='status-meta'>{{ readyCount }} 个资源在线</span>
            </div>
          </div>

          <h1 class='hero-title'>
            <span class='grad-text'>让模型</span>
            <span class='grad-text alt'>拥有超能力</span>
          </h1>
          <p class='hero-tag'>一句话启动 MCP，让 Agent 从“聊天”走进你的工具、文件、数据。</p>

          <div class='hero-stats'>
            <button class='stat' @click='pickTab("presets")'>
              <span class='stat-num'>{{ presets.length }}</span>
              <span class='stat-label'>预设</span>
              <span class='stat-tag'>→ 一键启用</span>
            </button>
            <button class='stat' :class='{ active: enabledCount > 0 }' @click='pickTab("servers")'>
              <span class='stat-num'>{{ enabledCount }}</span>
              <span class='stat-label'>已启用</span>
              <span class='stat-tag'>→ 管理</span>
            </button>
            <button class='stat' @click='pickTab("servers")'>
              <span class='stat-num'>{{ servers.length }}</span>
              <span class='stat-label'>总服务</span>
              <span class='stat-tag'>→ 查看</span>
            </button>
          </div>

          <div class='hero-quick'>
            <n-input v-model:value='quickPrompt' placeholder='试试问：“查询仓库本周增加的 star” — 需先启用 MCP' size='large' round @keyup.enter='quickStart'>
              <template #prefix>
                <span class='quick-emoji'>✨</span>
              </template>
            </n-input>
            <n-button type='primary' size='large' round @click='quickStart'>发起试试</n-button>
            <n-button size='large' round quaternary @click='openCreate'>
              <span style='font-weight:600'>+</span>&nbsp;添加 MCP
            </n-button>
          </div>

          <div class='hero-chips'>
            <button v-for='(p, i) in suggestedPrompts' :key='i' class='chip' @click='quickPrompt = p'>{{ p }}</button>
          </div>
        </div>
      </section>

      <n-alert v-if='errorMessage' class='mcp-alert' type='error' :show-icon='false'>
        {{ errorMessage }}
      </n-alert>

      <n-tabs v-model:value='tab' type='line' animated class='mcp-tabs'>
        <n-tab-pane name='presets' :tab='"预设库"'>
          <div class='section-heading'>
            <div>
              <h2>推荐预设</h2>
              <p>一键加入。加入后会被模型自动发现，随时可调用。</p>
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
                <n-tag v-if='installedIds.has(preset.id)' size='tiny' type='success' round class='installed-tag'>已添加</n-tag>
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
        </n-tab-pane>

        <n-tab-pane name='servers' :tab='"我的服务"'>
          <div class='section-heading'>
            <div>
              <h2>已配置的 MCP</h2>
              <p>点击「测试」可立即校验连通性，验证后会被模型自动调用。</p>
            </div>
            <span class='section-meta'>{{ serverCountLabel }}</span>
          </div>
          <div v-if='!servers.length' class='empty-block large'>
            <div class='empty-icon'>✦</div>
            <h3>还没有 MCP 服务</h3>
            <p>从预设库一键安装，或者手动添加。</p>
            <n-button type='primary' round @click='openCreate'>手动添加</n-button>
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
                <n-popconfirm @positive-click='removeServer(server)'>
                  <template #trigger>
                    <n-button size='small' quaternary type='error' @click.stop>删除</n-button>
                  </template>
                  确定删除「{{ server.name }}」？
                </n-popconfirm>
              </div>
            </article>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-spin>

    <n-modal v-model:show='editorOpen' preset='card' :title='editingId ? "编辑 MCP" : "添加 MCP"' class='mcp-editor' :bordered='false' size='huge'>
      <div class='editor-grid'>
        <section class='editor-col'>
          <h4>基本信息</h4>
          <n-input v-model:value='form.name' placeholder='名称，例如：本地文件' />
          <n-input v-model:value='form.description' type='textarea' :autosize='{ minRows: 2, maxRows: 4 }' placeholder='用途说明（可选）' />
        </section>
        <section class='editor-col'>
          <h4>传输方式</h4>
          <n-select v-model:value='form.transport' :options='transportOptions' />
          <n-input v-if='form.transport === "stdio"' v-model:value='form.command' placeholder='启动命令，例如：npx' />
          <n-input v-if='form.transport === "http"' v-model:value='form.url' placeholder='http://127.0.0.1:3000/mcp' />
        </section>
        <section class='editor-col'>
          <h4>启动参数</h4>
          <n-input v-if='form.transport === "stdio"' v-model:value='argsText' type='textarea' :autosize='{ minRows: 3, maxRows: 8 }' placeholder='JSON 字符串数组，例如：["-y","@scope/server"]' />
          <p v-else class='editor-hint'>HTTP 模式无需 args。</p>
        </section>
        <section class='editor-col'>
          <h4>环境变量</h4>
          <n-input v-model:value='envText' type='textarea' :autosize='{ minRows: 3, maxRows: 8 }' placeholder='JSON 对象，例如：{"TOKEN": "xxx"}' />
        </section>
      </div>
      <template #footer>
        <n-space justify='end'>
          <n-button quaternary @click='editorOpen = false'>取消</n-button>
          <n-button type='primary' :loading='saving' @click='saveServer'>保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.mcp-page { height: 100%; overflow-y: auto; padding: 0 28px 56px; box-sizing: border-box; background: radial-gradient(1100px 480px at 90% -10%, rgba(99, 102, 241, .14), transparent 60%), radial-gradient(900px 380px at -10% 0%, rgba(56, 189, 248, .10), transparent 55%); }
.hero { position: relative; overflow: hidden; margin: 28px 0 26px; padding: 28px 30px 32px; border: 1px solid var(--border-soft); border-radius: 22px; background: linear-gradient(135deg, rgba(99, 102, 241, .16), rgba(56, 189, 248, .06) 55%, rgba(255, 255, 255, 0)), var(--bg-elevated); box-shadow: 0 18px 48px rgba(15, 23, 42, .12); isolation: isolate; }
.hero-particles { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 0; pointer-events: auto; }
.hero-glow { position: absolute; inset: -25% -25% auto auto; width: 480px; height: 480px; background: radial-gradient(circle, rgba(99, 102, 241, .35), transparent 60%); filter: blur(20px); pointer-events: none; z-index: 0; animation: heroDrift 16s ease-in-out infinite alternate; }
.hero-grid { position: absolute; inset: 0; background-image: linear-gradient(to right, rgba(99, 102, 241, .07) 1px, transparent 1px), linear-gradient(to bottom, rgba(99, 102, 241, .07) 1px, transparent 1px); background-size: 32px 32px; mask-image: radial-gradient(circle at 50% 0%, #000 35%, transparent 80%); -webkit-mask-image: radial-gradient(circle at 50% 0%, #000 35%, transparent 80%); pointer-events: none; z-index: 0; }
@keyframes heroDrift { from { transform: translate3d(-4%, -2%, 0) scale(1); } to { transform: translate3d(4%, 2%, 0) scale(1.08); } }
.hero-inner { position: relative; z-index: 1; display: flex; flex-direction: column; gap: 14px; }
.hero-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.hero-badge { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px 6px 8px; border-radius: 999px; background: linear-gradient(135deg, rgba(99, 102, 241, .22), rgba(56, 189, 248, .18)); border: 1px solid rgba(99, 102, 241, .3); color: var(--text-primary); font-size: 12px; letter-spacing: .5px; font-weight: 600; box-shadow: 0 6px 18px rgba(99, 102, 241, .25); }
.badge-dot { width: 8px; height: 8px; border-radius: 50%; background: #a5b4fc; box-shadow: 0 0 12px #a5b4fc; animation: badgePulse 1.6s ease-in-out infinite; }
.badge-text { letter-spacing: .8px; }
@keyframes badgePulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .6; transform: scale(.85); } }
.hero-status { display: inline-flex; align-items: center; gap: 10px; }
.status-pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; font-size: 11px; color: var(--text-secondary); border: 1px solid rgba(34, 197, 94, .25); background: rgba(34, 197, 94, .08); border-radius: 999px; }
.status-pill.ok { color: #4ade80; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; animation: badgePulse 1.4s ease-in-out infinite; }
.status-meta { font-size: 11px; color: var(--text-muted); }
.hero-title { margin: 4px 0 0; font-size: clamp(28px, 4.4vw, 44px); line-height: 1.15; font-weight: 800; letter-spacing: -.5px; display: flex; flex-wrap: wrap; gap: 12px 18px; }
.grad-text { background-image: linear-gradient(120deg, #818cf8 0%, #38bdf8 50%, #c084fc 100%); -webkit-background-clip: text; background-clip: text; color: transparent; -webkit-text-fill-color: transparent; }
.grad-text.alt { background-image: linear-gradient(120deg, #38bdf8 0%, #818cf8 45%, #f472b6 100%); -webkit-background-clip: text; background-clip: text; color: transparent; -webkit-text-fill-color: transparent; }
.hero-tag { margin: 0; font-size: 14px; color: var(--text-secondary); line-height: 1.6; max-width: 60ch; }
.hero-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 4px; }
.stat { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 14px 16px; border: 1px solid var(--border-soft); border-radius: 14px; background: rgba(255, 255, 255, .03); color: inherit; cursor: pointer; text-align: left; transition: transform .18s ease, border-color .18s ease, background .18s ease; }
.stat:hover { transform: translateY(-2px); border-color: rgba(99, 102, 241, .5); background: rgba(99, 102, 241, .08); }
.stat.active { border-color: rgba(34, 197, 94, .55); background: rgba(34, 197, 94, .08); }
.stat-num { font-size: 26px; font-weight: 800; letter-spacing: -.5px; background-image: linear-gradient(135deg, #818cf8, #38bdf8); -webkit-background-clip: text; background-clip: text; color: transparent; line-height: 1; }
.stat-label { font-size: 12px; color: var(--text-muted); letter-spacing: .4px; }
.stat-tag { margin-top: 4px; font-size: 11px; color: var(--text-secondary); opacity: .7; transition: opacity .15s ease, transform .15s ease; }
.stat:hover .stat-tag { opacity: 1; transform: translateX(2px); }
.hero-quick { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 10px; align-items: center; margin-top: 6px; }
.quick-emoji { font-size: 16px; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid var(--border-soft); background: rgba(255, 255, 255, .04); color: var(--text-secondary); padding: 5px 10px; border-radius: 999px; font-size: 11px; cursor: pointer; transition: border-color .15s ease, color .15s ease, background .15s ease; }
.chip:hover { border-color: rgba(99, 102, 241, .5); color: var(--text-primary); background: rgba(99, 102, 241, .1); }
.mcp-alert { margin-bottom: 14px; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin: 22px 0 14px; }
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
.install-pill { font-size: 11px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border-soft); color: var(--text-secondary); background: transparent; transition: border-color .15s ease, background .15s ease, color .15s ease; }
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
.mcp-editor { width: min(760px, calc(100vw - 32px)); }
.editor-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 22px; }
.editor-col { display: flex; flex-direction: column; gap: 10px; }
.editor-col h4 { margin: 0 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .8px; color: var(--text-muted); font-weight: 600; }
.editor-hint { margin: 0; padding: 10px 12px; border-radius: 10px; background: var(--hover-bg); color: var(--text-muted); font-size: 12px; }
@media (max-width: 920px) { .hero { padding: 22px 22px 26px; } .hero-stats { grid-template-columns: 1fr 1fr; } .hero-quick { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .mcp-page { padding: 0 14px 30px; } .hero-stats { grid-template-columns: 1fr; } .preset-grid { grid-template-columns: 1fr; } }
</style>
