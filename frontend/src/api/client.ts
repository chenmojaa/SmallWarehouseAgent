const BASE = "/api"
const KEY_STORAGE = "second_brain_api_key"
const TOKEN_KEY = "hd_auth_token"

export function getApiKey(): string {
  try { return localStorage.getItem(KEY_STORAGE) || "" }
  catch { return "" }
}

export function setApiKey(k: string) {
  try {
    if (k) localStorage.setItem(KEY_STORAGE, k)
    else localStorage.removeItem(KEY_STORAGE)
  } catch {}
}

/** 401 时清除登录态并跳转登录页（已在登录页时不重复跳转） */
function handleUnauthorized() {
  try { localStorage.removeItem(TOKEN_KEY) } catch {}
  if (window.location.pathname !== "/login") {
    window.location.href = "/login"
  }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const k = getApiKey().trim()
  if (k) headers["X-API-Key"] = k
  try {
    const t = (localStorage.getItem(TOKEN_KEY) || "").trim()
    if (t) headers["X-Auth-Token"] = t
  } catch {}
  return headers
}

/** 仅登录 token 头，供 FormData 上传等场景与其它头合并 */
export function authTokenHeaders(): Record<string, string> {
  try {
    const t = (localStorage.getItem(TOKEN_KEY) || "").trim()
    if (t) return { "X-Auth-Token": t }
  } catch {}
  return {}
}

export async function get<T>(path: string): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) await new Promise(resolve => setTimeout(resolve, attempt * 700))
    let res: Response
    try {
      res = await fetch(BASE + path, { headers: { ...authHeaders() } })
    } catch (error) {
      lastError = error
      continue
    }
    if (res.ok) return res.json() as Promise<T>
    if (res.status === 401) { handleUnauthorized(); break }
    lastError = new Error(res.status + " " + (await res.text()))
    if (res.status < 500) break
  }
  throw lastError
}

function throwIfUnauthorized(status: number) {
  if (status === 401) handleUnauthorized()
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  })
  throwIfUnauthorized(res.status)
  if (!res.ok) throw new Error(res.status + " " + (await res.text()))
  return res.json() as Promise<T>
}

export async function postJsonPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  })
  throwIfUnauthorized(res.status)
  if (!res.ok) throw new Error(res.status + " " + (await res.text()))
  return res.json() as Promise<T>
}

export async function deleteReq(path: string): Promise<unknown> {
  const res = await fetch(BASE + path, { method: "DELETE", headers: { ...authHeaders() } })
  throwIfUnauthorized(res.status)
  if (!res.ok) throw new Error(res.status + " " + (await res.text()))
  return res.json()
}

export async function* streamSse(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<{ event: string; data: string }> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    throwIfUnauthorized(res.status)
    throw new Error("HTTP " + res.status)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let event = "message"

  let dataBuf: string[] = []
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const raw of lines) {
      const line = raw
      if (line.startsWith("event: ")) {
        event = line.slice(7).trim()
      } else if (line.startsWith("data: ")) {
        dataBuf.push(line.slice(6))
      } else if (line === "") {
        if (dataBuf.length > 0) {
          yield { event, data: dataBuf.join("\n") }
          dataBuf = []
          event = "message"
        }
      }
    }
  }
  if (dataBuf.length > 0) {
    yield { event, data: dataBuf.join("\n") }
  }
}
