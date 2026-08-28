import { defineStore } from 'pinia'
import {
  listCustomModels,
  createCustomModel,
  updateCustomModel,
  deleteCustomModel,
  setSelectedModel,
  type CustomModelEntry,
  type ReasoningLevel,
  type CreatePayload,
} from '@/api/custom-models'

export type { ReasoningLevel, CustomModelEntry }

// Legacy localStorage keys (kept so we can migrate old data on first load).
const LEGACY_LIST_KEY = 'sb_custom_models'
const LEGACY_SELECTED_KEY = 'sb_selected_model'
const MODELS_CACHE_KEY = 'hd_models_cache_v1'

interface State {
  list: CustomModelEntry[]
  selectedId: string | null
  loading: boolean
  loaded: boolean
  lastError: string | null
  filePath: string | null
}

function parseLegacy(raw: string | null): CustomModelEntry[] {
  if (!raw) return []
  try {
    const j = JSON.parse(raw)
    if (Array.isArray(j)) return j as CustomModelEntry[]
    if (j && Array.isArray(j.items)) return j.items as CustomModelEntry[]
  } catch {
    return []
  }
  return []
}

function readModelsCache(): { items: CustomModelEntry[]; selectedId: string | null } {
  try {
    const raw = localStorage.getItem(MODELS_CACHE_KEY)
    const value = raw ? JSON.parse(raw) : null
    if (value && Array.isArray(value.items)) {
      return { items: value.items, selectedId: value.selectedId ?? null }
    }
  } catch {}
  return { items: [], selectedId: null }
}

function writeModelsCache(items: CustomModelEntry[], selectedId: string | null) {
  try { localStorage.setItem(MODELS_CACHE_KEY, JSON.stringify({ items, selectedId })) } catch {}
}

export const useModelsStore = defineStore('models', {
  state: (): State => ({
    list: [],
    selectedId: null,
    loading: false,
    loaded: false,
    lastError: null,
    filePath: null,
  }),
  getters: {
    selected(state): (CustomModelEntry & { modelName: string; reasoning: ReasoningLevel }) | null {
      const e = state.list.find(x => x.id === state.selectedId) || state.list[0]
      if (!e) return null
      const m = e.models.find(x => x.name === e.defaultModel) || e.models[0]
      return { ...e, modelName: m?.name || '', reasoning: m?.reasoning || 'medium' }
    },
  },
  actions: {
    /** Pull the list from the backend. Safe to call multiple times. */
    async loadFromBackend() {
      if (this.loading) return
      this.loading = true
      this.lastError = null
      try {
        // If we have legacy localStorage entries AND the backend is empty,
        // migrate them up so the user doesn't lose their old data.
        const legacyList = parseLegacy(localStorage.getItem(LEGACY_LIST_KEY))
        const legacySelected = localStorage.getItem(LEGACY_SELECTED_KEY)

        const r = await listCustomModels()
        this.filePath = r.path ?? null

        if (r.items.length === 0 && legacyList.length > 0) {
          // Push legacy entries to backend.
          for (const e of legacyList) {
            const payload: CreatePayload = {
              name: e.name,
              baseUrl: e.baseUrl,
              apiKey: e.apiKey,
              provider: e.provider,
              models: e.models,
              defaultModel: e.defaultModel,
              embeddingModel: e.embeddingModel ?? null,
            }
            try { await createCustomModel(payload) }
            catch (err) { console.warn('[models] legacy migration failed for', e.name, err) }
          }
          // Re-fetch to pick up the server-assigned ids.
          const r2 = await listCustomModels()
          this.list = r2.items
          this.selectedId = r2.selected_id ?? this.list[0]?.id ?? null
        } else {
          this.list = r.items
          this.selectedId = r.selected_id ?? this.list[0]?.id ?? null
          // If we had a legacy selection that doesn't match any current id,
          // also restore it (best effort).
          if (legacySelected && !this.selectedId && this.list.some(x => x.id === legacySelected)) {
            this.selectedId = legacySelected
          }
        }
        writeModelsCache(this.list, this.selectedId)

        // Drop the legacy cache once we have backend state.
        try {
          localStorage.removeItem(LEGACY_LIST_KEY)
          localStorage.removeItem(LEGACY_SELECTED_KEY)
        } catch {}

        this.loaded = true
      } catch (e) {
        this.lastError = (e as Error).message || String(e)
        console.error('[models] loadFromBackend failed:', this.lastError)
        const cached = readModelsCache()
        if (cached.items.length > 0) {
          this.list = cached.items
          this.selectedId = cached.selectedId && cached.items.some(x => x.id === cached.selectedId)
            ? cached.selectedId
            : cached.items[0]?.id ?? null
          this.loaded = true
        }
      } finally {
        this.loading = false
      }
    },

    async add(entry: Omit<CustomModelEntry, 'id' | 'createdAt'>): Promise<boolean> {
      this.lastError = null
      // Optimistic insert
      const placeholder: CustomModelEntry = {
        ...(entry as CustomModelEntry),
        id: 'pending-' + Date.now(),
        createdAt: new Date().toISOString(),
      }
      this.list.push(placeholder)
      if (!this.selectedId) this.selectedId = placeholder.id

      try {
        const saved = await createCustomModel(entry)
        const i = this.list.findIndex(x => x.id === placeholder.id)
        if (i >= 0) this.list[i] = saved
        if (this.selectedId === placeholder.id) this.selectedId = saved.id
        writeModelsCache(this.list, this.selectedId)
        return true
      } catch (e) {
        // Rollback
        this.list = this.list.filter(x => x.id !== placeholder.id)
        if (this.selectedId === placeholder.id) {
          this.selectedId = this.list[0]?.id ?? null
        }
        this.lastError = (e as Error).message || String(e)
        return false
      }
    },

    async update(id: string, patch: Partial<CustomModelEntry>): Promise<boolean> {
      this.lastError = null
      const i = this.list.findIndex(x => x.id === id)
      const original = i >= 0 ? { ...this.list[i] } : null
      if (i >= 0) this.list[i] = { ...this.list[i], ...patch }

      try {
        const saved = await updateCustomModel(id, patch)
        if (i >= 0) this.list[i] = saved
        writeModelsCache(this.list, this.selectedId)
        return true
      } catch (e) {
        if (i >= 0 && original) this.list[i] = original
        this.lastError = (e as Error).message || String(e)
        return false
      }
    },

    async remove(id: string): Promise<boolean> {
      this.lastError = null
      const originalList = [...this.list]
      const wasSelected = this.selectedId === id
      this.list = this.list.filter(x => x.id !== id)
      if (wasSelected) {
        this.selectedId = this.list[0]?.id ?? null
      }

        try {
          await deleteCustomModel(id)
          if (wasSelected) await setSelectedModel(this.selectedId)
          writeModelsCache(this.list, this.selectedId)
        return true
      } catch (e) {
        this.list = originalList
        if (wasSelected) this.selectedId = id
        this.lastError = (e as Error).message || String(e)
        return false
      }
    },

    async select(id: string | null): Promise<boolean> {
      this.lastError = null
      const original = this.selectedId
      this.selectedId = id
      try {
        await setSelectedModel(id)
        writeModelsCache(this.list, this.selectedId)
        return true
      } catch (e) {
        this.selectedId = original
        this.lastError = (e as Error).message || String(e)
        return false
      }
    },

    forceFlush(): Promise<boolean> {
      // No-op for backend-backed store; reload picks up server state.
      return this.loadFromBackend().then(() => true)
    },
    debugReadStorage(): string | null {
      return this.filePath
    },
  },
})
