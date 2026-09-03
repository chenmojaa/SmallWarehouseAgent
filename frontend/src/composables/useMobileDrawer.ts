import { ref } from 'vue'
const _open = ref(false)
export const sidebarDrawerOpen = _open
export function toggleSidebarDrawer() { _open.value = !_open.value }
export function openSidebarDrawer() { _open.value = true }
export function closeSidebarDrawer() { _open.value = false }
