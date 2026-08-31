const BASE = "/api"

export interface AuthResult {
  ok: boolean
  user_id: number
  phone: string
  token?: string
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

export function register(phone: string, password: string): Promise<AuthResult> {
  return post<AuthResult>("/auth/register", { phone, password })
}

export function login(account: string, password: string): Promise<AuthResult> {
  return post<AuthResult>("/auth/login", { account, password })
}

export function changePassword(phone: string, newPassword: string): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>("/auth/change-password", { phone, new_password: newPassword })
}
