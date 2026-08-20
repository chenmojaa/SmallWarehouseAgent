import { get, postJson, postJsonPatch, deleteReq } from './client'

export type ReasoningLevel = 'low' | 'medium' | 'high' | 'xhigh'

export interface SubModelSpec {
  name: string
  reasoning: ReasoningLevel
}

export interface CustomModelEntry {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  provider: string
  models: SubModelSpec[]
  defaultModel: string
  embeddingModel?: string | null
  createdAt: string
}

export interface ListResponse {
  items: CustomModelEntry[]
  selected_id: string | null
  path?: string
}

export async function listCustomModels(): Promise<ListResponse> {
  return get<ListResponse>('/custom-models')
}

export interface CreatePayload {
  name: string
  baseUrl: string
  apiKey: string
  provider: string
  models: SubModelSpec[]
  defaultModel?: string | null
  embeddingModel?: string | null
}

export async function createCustomModel(payload: CreatePayload): Promise<CustomModelEntry> {
  return postJson<CustomModelEntry>('/custom-models', payload)
}

export async function updateCustomModel(id: string, patch: Partial<CustomModelEntry>): Promise<CustomModelEntry> {
  return postJsonPatch<CustomModelEntry>(`/custom-models/${id}`, patch)
}

export async function deleteCustomModel(id: string): Promise<{ deleted: string }> {
  return deleteReq(`/custom-models/${id}`) as Promise<{ deleted: string }>
}

export async function setSelectedModel(id: string | null): Promise<{ selected: string | null }> {
  return postJson('/custom-models/selected', { id })
}

// Legacy: detect model list from a custom OpenAI-compatible endpoint.
// Lives at a different backend endpoint (/settings/custom-models), separate
// from the CRUD in this file. Kept here for backward compat with SettingsView.
export interface CustomModelsResponse {
  provider: string
  base_url: string
  models: string[]
}

export interface CustomModelsRequest {
  base_url: string
  api_key: string
}

export async function detectModels(req: CustomModelsRequest): Promise<CustomModelsResponse> {
  return postJson<CustomModelsResponse>('/settings/custom-models', req)
}

export { get }
