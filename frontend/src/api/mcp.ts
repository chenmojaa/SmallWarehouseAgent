import { deleteReq, get, postJson, postJsonPatch } from './client'

export interface MCPPreset {
  id: string
  name: string
  name_zh: string
  description: string
  emoji: string
  category: string
  transport: 'stdio' | 'http'
  command: string
  args: string[]
  env: Record<string, string>
  requirements: string
  installed: boolean
}

export interface MCPServer {
  id: string
  preset_id: string
  name: string
  transport: 'stdio' | 'http'
  command: string
  args: string[]
  env: Record<string, string>
  url: string
  description: string
  enabled: boolean
  created_at: string
  updated_at: string
  last_test_at: string | null
  last_test_ok: boolean | null
  last_test_message: string
}

export interface MCPServerPayload {
  name: string
  transport: 'stdio' | 'http'
  command: string
  args: string[]
  env: Record<string, string>
  url: string
  description: string
  enabled: boolean
}

export function listMcpPresets(): Promise<{ items: MCPPreset[] }> {
  return get('/mcp/presets')
}

export function listMcpServers(): Promise<{ items: MCPServer[] }> {
  return get('/mcp')
}

export function installMcpPreset(id: string): Promise<{ item: MCPServer; created: boolean }> {
  return postJson(`/mcp/presets/${encodeURIComponent(id)}`, {})
}

export function createMcpServer(payload: MCPServerPayload): Promise<MCPServer> {
  return postJson('/mcp', payload)
}

export function updateMcpServer(id: string, patch: Partial<MCPServerPayload>): Promise<MCPServer> {
  return postJsonPatch(`/mcp/${encodeURIComponent(id)}`, patch)
}

export function testMcpServer(id: string): Promise<{ ok: boolean; message: string; item: MCPServer }> {
  return postJson(`/mcp/${encodeURIComponent(id)}/test`, {})
}

export function deleteMcpServer(id: string): Promise<{ ok: boolean }> {
  return deleteReq(`/mcp/${encodeURIComponent(id)}`) as Promise<{ ok: boolean }>
}
