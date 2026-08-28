import { get, postJson } from './client'

export interface FeishuStatus {
  enabled: boolean
  app_id_set: boolean
  app_secret_set: boolean
  api_base: string
  space_ids: string[]
  sync_interval_min: number
}

export interface FeishuSpace {
  space_id: string
  name?: string
  description?: string
  visibility?: string
  space_type?: string
}

export interface FeishuSyncResult {
  space_id: string
  space_name: string
  synced: number
  updated: number
  skipped: number
  failed: number
  errors?: string[]
}

export interface FeishuSyncResponse {
  results: FeishuSyncResult[]
}

export function getFeishuStatus(): Promise<FeishuStatus> {
  return get<FeishuStatus>('/feishu/status')
}

export function listFeishuSpaces(): Promise<{ items: FeishuSpace[] }> {
  return get<{ items: FeishuSpace[] }>('/feishu/spaces')
}

export function syncFeishu(spaceId?: string | null): Promise<FeishuSyncResponse> {
  return postJson<FeishuSyncResponse>('/feishu/sync', {
    space_id: spaceId || null,
    force_full: false,
  })
}

export interface FeishuConfig {
  web_url: string
  app_id: string
  app_secret_set: boolean
  app_secret_masked: string
  api_base: string
  space_ids: string[]
  enabled: boolean
  configured: boolean
  sync_interval_min: number
}

export interface FeishuConfigPatch {
  web_url?: string
  app_id?: string
  app_secret?: string
  api_base?: string
  space_ids?: string
}

export interface FeishuTestResult {
  ok: boolean
  spaces: { space_id: string; name?: string }[]
}

export function getFeishuConfig(): Promise<FeishuConfig> {
  return get<FeishuConfig>("/feishu/config")
}

export function updateFeishuConfig(patch: FeishuConfigPatch): Promise<FeishuConfig> {
  return postJson<FeishuConfig>("/feishu/config", patch)
}

export function testFeishuConnection(): Promise<FeishuTestResult> {
  return postJson<FeishuTestResult>("/feishu/test", {})
}
