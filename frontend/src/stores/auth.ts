import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { markAuthed, markLoggedOut } from '@/router'
import * as authApi from '@/api/auth'

const TOKEN_KEY = 'hd_auth_token'
const PHONE_KEY = 'hd_auth_phone'

function readToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(readToken())
  const phone = ref((() => { try { return localStorage.getItem(PHONE_KEY) || '' } catch { return '' } })())
  const isLoggedIn = computed(() => !!token.value)

  function setAuth(t: string, p: string) {
    token.value = t
    phone.value = p
    try {
      localStorage.setItem(TOKEN_KEY, t)
      localStorage.setItem(PHONE_KEY, p)
    } catch {}
    markAuthed()
  }

  /**
   * Logout: tell the server to revoke the token (so it can't be reused
   * on another device), then drop local state.
   */
  async function logout() {
    try { await authApi.logout() } catch {}
    token.value = ''
    phone.value = ''
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(PHONE_KEY)
    } catch {}
    markLoggedOut()
  }

  return { token, phone, isLoggedIn, setAuth, logout }
})