import { createRouter, createWebHistory } from 'vue-router'

const TOKEN_KEY = 'hd_auth_token'

function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}

function clearToken(): void {
  try { localStorage.removeItem(TOKEN_KEY) } catch {}
}

/** 本地快速检查：token 格式为 `userId.exp.sig`，先看是否已过期（毫秒级） */
function isTokenLocallyValid(token: string | null): boolean {
  if (!token) return false
  const parts = token.split('.')
  if (parts.length !== 3) return false
  const exp = Number(parts[1])
  return Number.isFinite(exp) && Date.now() < exp * 1000
}

// 每次页面加载只做一次服务端校验，结果缓存在内存中（导航不重复请求）
let authVerified: boolean | null = null

/** 服务端校验 token 有效性（调 /api/auth/me） */
async function verifyWithServer(token: string): Promise<boolean> {
  try {
    const res = await fetch('/api/auth/me', { headers: { 'X-Auth-Token': token } })
    return res.ok
  } catch {
    // 网络异常时保守放行，后续 API 401 会兜底跳转
    return true
  }
}

async function isAuthed(): Promise<boolean> {
  const token = getToken()
  // 本地过期/格式错误：直接视为未登录，不必请求服务端
  if (!token || !isTokenLocallyValid(token)) {
    clearToken()
    authVerified = false
    return false
  }
  if (authVerified !== null) return authVerified
  authVerified = await verifyWithServer(token)
  if (!authVerified) clearToken()
  return authVerified
}

// 登录成功后调用，重置校验缓存
export function markAuthed(): void {
  authVerified = true
}

export function markLoggedOut(): void {
  authVerified = false
  clearToken()
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/chat" },
    { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"), meta: { public: true } },
    { path: "/chat", name: "chat", component: () => import("@/views/ChatView.vue") },
    { path: "/chat/:id", name: "chat-id", component: () => import("@/views/ChatView.vue") },
    { path: "/notes", name: "notes", component: () => import("@/views/NotesView.vue") },
    { path: "/settings", name: "settings", component: () => import("@/views/SettingsView.vue") },
    { path: "/skills-mcp", name: "skills-mcp", component: () => import("@/views/SkillsMcpView.vue") },
    { path: "/mcp", redirect: "/skills-mcp" },
  ],
})

// 路由守卫：真正校验登录态（本地过期检查 + 服务端验证），未登录一律跳转登录页
router.beforeEach(async (to) => {
  const authed = await isAuthed()
  if (to.meta.public) {
    // 已登录访问登录页时直接进入应用
    if (to.name === "login" && authed) return { path: "/chat" }
    return true
  }
  if (!authed) {
    return { name: "login", query: to.fullPath !== "/" ? { redirect: to.fullPath } : {} }
  }
  return true
})

export default router
