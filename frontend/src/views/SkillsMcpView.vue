<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import SkillsPanel from '@/components/SkillsPanel.vue'
import McpPanel from '@/components/McpPanel.vue'
import McpCallHistory from '@/components/McpCallHistory.vue'

const message = useMessage()
const tab = ref<'skills' | 'mcp' | 'history'>('skills')

const mcpPanelRef = ref<InstanceType<typeof McpPanel> | null>(null)
const skillsPanelRef = ref<InstanceType<typeof SkillsPanel> | null>(null)

const stats = computed(() => {
  const mcp = mcpPanelRef.value?.summary
  const skills = skillsPanelRef.value?.summary
  return {
    enabled: mcp?.enabled ?? 0,
    servers: mcp?.servers ?? 0,
    presets: mcp?.presets ?? 0,
    installed: skills?.installed ?? 0,
    recommended: skills?.recommended ?? 0,
  }
})

onMounted(() => {
  if (import.meta.env.DEV) {
    // expose for quick console debugging in dev builds only
    (window as any).__skillsMcpTab = tab
  }
})

function switchTab(name: 'skills' | 'mcp' | 'history') {
  tab.value = name
}
</script>

<template>
  <div class="skills-mcp-page">
    <header class="page-top">
      <div class="top-tabs">
        <button class="top-tab" :class="{ active: tab === 'skills' }" @click="switchTab('skills')">
          <span class="tab-emoji">🧩</span>技能
        </button>
        <button class="top-tab" :class="{ active: tab === 'mcp' }" @click="switchTab('mcp')">
          <span class="tab-emoji">🔌</span>MCP
        </button>
      </div>
      <div class="top-meta">
        <span class="meta-pill">技能 {{ stats.installed }}/{{ stats.recommended + stats.installed }}</span>
        <span class="meta-pill">MCP {{ stats.enabled }}/{{ stats.servers }} 启用</span>
        <span class="meta-pill">预设 {{ stats.presets }}</span>
      </div>
    </header>

    <div class="page-body">
      <SkillsPanel v-show="tab === 'skills'" ref="skillsPanelRef" />
      <McpPanel v-show="tab === 'mcp'" ref="mcpPanelRef" />
    </div>
  </div>
</template>

<style scoped>
.skills-mcp-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.page-top {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 28px 14px;
  border-bottom: 1px solid var(--border-soft);
  background: var(--bg-app);
}
.top-tabs {
  display: inline-flex;
  gap: 6px;
  padding: 5px;
  border-radius: 12px;
  background: var(--hover-bg);
}
.top-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 22px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all .18s ease;
}
.top-tab:hover { color: var(--text-primary); }
.top-tab.active {
  color: var(--text-primary);
  font-weight: 600;
  background: var(--bg-elevated);
  box-shadow: 0 1px 5px rgba(15, 23, 42, .09);
}
.tab-emoji { font-size: 15px; }
.top-meta { display: flex; align-items: center; gap: 8px; }
.meta-pill {
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid var(--border-soft);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.page-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.page-body > :deep(*) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
@media (max-width: 720px) {
  .page-top { flex-direction: column; align-items: stretch; }
  .top-meta { justify-content: flex-start; flex-wrap: wrap; }
}
</style>
