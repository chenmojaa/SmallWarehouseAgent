import { get, postJson } from './client'

export interface ModelsInfo {
  providers: string[]
  current: {
    llm_provider: string
    llm_model: string
    llm_api_base: string
    embedding_provider: string
    embedding_model: string
  }
}

export function listModels() {
  return get<ModelsInfo>("/settings/models")
}

export interface LlmConfig {
  api_key_set: boolean
  api_key_masked: string
  base_url: string
}

export function getLlmConfig() {
  return get<LlmConfig>("/settings/llm-config")
}

export function saveLlmConfig(patch: { api_key?: string; base_url?: string }) {
  return postJson<LlmConfig>("/settings/llm-config", patch)
}