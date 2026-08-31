import { createRouter, createWebHistory } from 'vue-router'

const TOKEN_KEY = 'hd_auth_token'

function hasToken(): boolean {
  try { return !!localStorage.getItem(TOKEN_KEY) } catch { return false }
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
  ],
})

// 路由守卫：未登录一律跳转登录页
router.beforeEach((to) => {
  if (to.meta.public) {
    // 已登录访问登录页时直接进入应用
    if (to.name === "login" && hasToken()) return { path: "/chat" }
    return true
  }
  if (!hasToken()) {
    return { name: "login", query: to.fullPath !== "/" ? { redirect: to.fullPath } : {} }
  }
  return true
})

export default router
