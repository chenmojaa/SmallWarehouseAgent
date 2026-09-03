import { ref } from 'vue'

const _open = ref(false)
const _listeners = new Set<(v: boolean) => void>()

export function open() { _open.value = true; _listeners.forEach(fn => fn(true)) }
export function close() { _open.value = false; _listeners.forEach(fn => fn(false)) }
export function subscribe(fn: (v: boolean) => void): () => void {
  _listeners.add(fn)
  fn(_open.value)
  return () => _listeners.delete(fn)
}
export const isOpen = _open
