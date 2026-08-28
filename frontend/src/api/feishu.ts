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
  enabled: boolean
  api_base: string
  sync_interval_min: number
}

export function getFeishuConfig(): Promise<FeishuConfig> {
  return get<FeishuConfig>("/feishu/config")
}

export function updateFeishuConfig(web_url: string): Promise<FeishuConfig> {
  return postJson<FeishuConfig>("/feishu/config", { web_url })
}
