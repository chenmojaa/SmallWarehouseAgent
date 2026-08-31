import { defineStore } from 'pinia'
import {
  listNotes, getStats, ingestUrl, ingestText, deleteNote,
  ingestFile, ingestImage, reembedNote,
  type Note, type NotesStats,
} from '@/api/notes'

interface State {
  items: Note[]
  total: number
  stats: NotesStats | null
  loading: boolean
  ingesting: boolean
  error: string | null
  uploadProgress: { name: string; status: 'uploading' | 'done' | 'failed' | 'canceled'; message?: string } | null
  uploadAbort: AbortController | null
}

export const useNotesStore = defineStore('notes', {
  state: (): State => ({
    items: [],
    total: 0,
    stats: null,
    loading: false,
    ingesting: false,
    error: null,
    uploadProgress: null,
    uploadAbort: null,
  }),
  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        const data = await listNotes()
        this.items = data.items
        this.total = data.total
      } catch (e) {
        this.error = (e as Error).message
      } finally {
        this.loading = false
      }
    },
    async refreshStats() {
      try {
        this.stats = await getStats()
      } catch (e) {
        this.error = (e as Error).message
      }
    },
    async addUrl(url: string) {
      this.ingesting = true
      this.error = null
      try {
        const note = await ingestUrl(url)
        this.items.unshift(note)
        this.total += 1
        await this.refreshStats()
        return note
      } catch (e) {
        this.error = (e as Error).message
        throw e
      } finally {
        this.ingesting = false
      }
    },
    async addText(text: string, title?: string) {
      this.ingesting = true
      this.error = null
      try {
        const note = await ingestText(text, title)
        this.items.unshift(note)
        this.total += 1
        await this.refreshStats()
        return note
      } catch (e) {
        this.error = (e as Error).message
        throw e
      } finally {
        this.ingesting = false
      }
    },
    async uploadFile(file: File) {
      const abort = new AbortController()
      this.uploadAbort = abort
      this.uploadProgress = { name: file.name, status: 'uploading' }
      this.error = null
      try {
        const name = file.name.toLowerCase()
        let note
        if (name.match(/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/)) {
          note = await ingestImage(file, undefined, abort.signal)
        } else {
          note = await ingestFile(file, undefined, abort.signal)
        }
        this.items.unshift(note)
        this.total += 1
        this.uploadProgress = { name: file.name, status: 'done' }
        await this.refreshStats()
        setTimeout(() => { this.uploadProgress = null }, 2500)
        return note
      } catch (e) {
        // User-initiated abort -> show "canceled", not an error.
        if (abort.signal.aborted) {
          this.uploadProgress = { name: file.name, status: 'canceled' }
          setTimeout(() => { this.uploadProgress = null }, 2500)
          return null
        }
        this.uploadProgress = { name: file.name, status: 'failed', message: (e as Error).message }
        this.error = (e as Error).message
        setTimeout(() => { this.uploadProgress = null }, 5000)
        throw e
      } finally {
        this.uploadAbort = null
      }
    },
    cancelUpload() {
      if (this.uploadAbort) this.uploadAbort.abort()
    },
    async reembed(id: string) {
      const updated = await reembedNote(id)
      const i = this.items.findIndex(n => n.id === id)
      if (i >= 0) this.items[i] = updated
      await this.refreshStats()
      return updated
    },
    async remove(id: string) {
      try {
        await deleteNote(id)
        this.items = this.items.filter(n => n.id !== id)
        this.total = Math.max(0, this.total - 1)
        await this.refreshStats()
      } catch (e) {
        this.error = (e as Error).message
        throw e
      }
    },
  },
})