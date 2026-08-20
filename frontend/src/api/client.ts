const BASE = "/api"
const KEY_STORAGE = "second_brain_api_key"

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

function authHeaders(): Record<string, string> {
  const k = getApiKey().trim()
  return k ? { "X-API-Key": k } : {}
}

export async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { headers: { ...authHeaders() } })
  if (!res.ok) throw new Error(res.status + " " + (await res.text()))
  return res.json() as Promise<T>
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(res.status + " " + (await res.text()))
  return res.json() as Promise<T>
}

export async function postJsonPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(res.status + " " + (await res.text()))
  return res.json() as Promise<T>
}

export async function deleteReq(path: string): Promise<unknown> {
  const res = await fetch(BASE + path, { method: "DELETE", headers: { ...authHeaders() } })
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
  if (!res.ok || !res.body) throw new Error("HTTP " + res.status)

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