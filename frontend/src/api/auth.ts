const BASE = "/api"

export interface AuthResult {
  ok: boolean
  user_id: number
  phone: string
  token?: string
}

function getToken(): string {
  try { return localStorage.getItem('hd_auth_token') || '' } catch { return '' }
}

async function request<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (auth) {
    const t = getToken()
    if (t) headers["Authorization"] = "Bearer " + t
  }
  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let data: Record<string, unknown> = {}
  try { data = JSON.parse(text) } catch {}
  if (!res.ok) {
    let detail = text
    if (typeof data.detail === "string") detail = data.detail
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return data as T
}

async function post<T>(path: string, body: unknown, auth = false): Promise<T> {
  return request<T>("POST", path, body, auth)
}

export function register(phone: string, password: string): Promise<AuthResult> {
  return post<AuthResult>("/auth/register", { phone, password })
}

export function login(account: string, password: string): Promise<AuthResult> {
  return post<AuthResult>("/auth/login", { account, password })
}

/**
 * Change password by phone + old_password + new_password.
 * Server now requires the old password (security hardening in P0).
 */
export function changePassword(phone: string, oldPassword: string, newPassword: string): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>("/auth/change-password", { phone, old_password: oldPassword, new_password: newPassword })
}

/**
 * Logged-in change-password: pass only old + new (the token identifies who).
 * Server revokes the current token after success, so the next request will
 * need to re-login with the new password.
 */
export function changePasswordAuthed(oldPassword: string, newPassword: string): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>("/auth/change-password-authed", { old_password: oldPassword, new_password: newPassword }, true)
}

/** Logout: revoke the current token on the server. Falls back to local clear if it fails. */
export async function logout(): Promise<{ ok: boolean }> {
  try {
    return await post<{ ok: boolean }>("/auth/logout", {}, true)
  } catch {
    return { ok: true }
  }
}

/** GDPR data export. */
export function exportMyData(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("GET", "/auth/me/export", undefined, true)
}

/** GDPR delete-account. */
export function deleteMyAccount(): Promise<{ ok: boolean; removed_rows: number }> {
  return request<{ ok: boolean; removed_rows: number }>("DELETE", "/auth/me", undefined, true)
}