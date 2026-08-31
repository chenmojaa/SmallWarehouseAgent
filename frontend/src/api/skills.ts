import { get, postJson, deleteReq, authTokenHeaders } from './client'

export interface RecommendedSkill {
  id: string
  name: string
  description: string
  category: string
  emoji: string
  badge?: string
  source_url: string
  installed: boolean
}

export interface InstalledSkill {
  id: string
  name: string
  description: string
  file_count: number
  size_bytes: number
  source_type: 'folder' | 'archive' | 'github' | string
  source_label: string
  source_url?: string
  installed_at: string
}

export function listRecommendedSkills(): Promise<{ items: RecommendedSkill[] }> {
  return get('/skills/recommended')
}

export function listInstalledSkills(): Promise<{ items: InstalledSkill[] }> {
  return get('/skills')
}

export interface SkillDetail extends InstalledSkill {
  content: string
  files: string[]
}

export function getSkillDetail(id: string): Promise<SkillDetail> {
  return get(`/skills/${encodeURIComponent(id)}/detail`)
}

export function installRecommendedSkill(id: string): Promise<InstalledSkill> {
  return postJson(`/skills/install/${encodeURIComponent(id)}`, {})
}

export function removeInstalledSkill(id: string) {
  return deleteReq(`/skills/${encodeURIComponent(id)}`)
}

/** 下载已安装技能的 zip 包（携带登录 token） */
export async function downloadSkill(id: string): Promise<void> {
  const response = await fetch(`/api/skills/${encodeURIComponent(id)}/download`, {
    headers: { ...authTokenHeaders() },
  })
  if (!response.ok) throw new Error(await response.text())
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${id}.zip`
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function uploadSkillFiles(files: File[], sourceName?: string): Promise<{ items: InstalledSkill[] }> {
  const form = new FormData()
  if (sourceName) form.append('source_name', sourceName)
  files.forEach(file => {
    const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath
    form.append('files', file, relative || file.name)
  })
  const response = await fetch('/api/skills/upload', {
    method: 'POST',
    headers: { ...authTokenHeaders() },
    body: form,
  })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}
