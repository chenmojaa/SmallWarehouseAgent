<template>
  <div class="approval-card" :class="status">
    <div class="card-head">
      <span class="card-label">{{ t('chat.planApproval.title', '执行计划待确认', 'Plan awaiting review') }}</span>
      <span v-if="status === 'cancelled'" class="badge-cancelled">{{ t('chat.planApproval.cancelled', '已取消', 'Cancelled') }}</span>
    </div>
    <div v-if="summary" class="card-summary">{{ summary }}</div>

    <!-- pending：可编辑步骤列表 -->
    <div v-if="status === 'pending'" class="step-list">
      <div v-for="(s, i) in editSteps" :key="i" class="step-row">
        <span class="step-num">{{ i + 1 }}</span>
        <input
          v-model="editSteps[i]"
          class="step-input"
          type="text"
          :placeholder="t('chat.planApproval.stepPlaceholder', '检索子问题', 'sub-query')"
          maxlength="120"
        />
        <button
          type="button"
          class="step-del"
          :title="t('chat.planApproval.deleteStep', '删除此步骤', 'Delete step')"
          :disabled="editSteps.length <= 1"
          @click="removeStep(i)"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <button
        v-if="editSteps.length < maxSteps"
        type="button"
        class="add-step"
        @click="editSteps.push('')"
      >
        {{ t('chat.planApproval.addStep', '+ 添加步骤', '+ Add step') }}
      </button>
    </div>

    <!-- 非 pending：静态步骤 -->
    <div v-else class="card-steps">
      <span v-for="(s, i) in steps" :key="i" class="card-chip">
        <span class="chip-num">{{ i + 1 }}</span>
        <span class="chip-text">{{ s }}</span>
      </span>
    </div>

    <div v-if="status === 'pending'" class="card-actions">
      <button type="button" class="btn-run" :disabled="!hasSteps" @click="onRun">
        {{ t('chat.planApproval.run', '运行', 'Run') }}
      </button>
      <button type="button" class="btn-cancel" @click="emit('cancel')">
        {{ t('chat.planApproval.cancel', '取消', 'Cancel') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { t } from '@/i18n'

const props = defineProps<{
  summary: string
  steps: string[]
  status: 'pending' | 'approved' | 'cancelled'
  disabled?: boolean
}>()

const emit = defineEmits<{
  run: [steps: string[]]
  cancel: []
}>()

// 与后端 planner_max_steps 对齐（后端也会截断）
const maxSteps = 4

const editSteps = ref<string[]>([...props.steps])
// steps 变化时（新一条预览到达）重建编辑副本
watch(() => props.steps, (v) => { editSteps.value = [...v] })

const hasSteps = computed(() => editSteps.value.some(s => s.trim()))

function removeStep(i: number) {
  if (editSteps.value.length > 1) editSteps.value.splice(i, 1)
}

function onRun() {
  const cleaned = editSteps.value.map(s => s.trim()).filter(Boolean)
  if (!cleaned.length || props.disabled) return
  emit('run', cleaned)
}
</script>

<style scoped>
.approval-card {
  display: flex; flex-direction: column; gap: 8px;
  margin-bottom: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(59, 130, 246, 0.35);
  background: var(--bg-elevated, rgba(255, 255, 255, 0.04));
  max-width: 520px;
}
.approval-card.cancelled {
  border-color: var(--border-soft, rgba(255, 255, 255, 0.08));
  opacity: 0.65;
}
.card-head { display: flex; align-items: center; gap: 8px; }
.card-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.4px;
  color: var(--brand-blue, #3b82f6);
}
.badge-cancelled {
  font-size: 11px; padding: 1px 8px; border-radius: 999px;
  color: var(--text-muted, #777);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
}
.card-summary {
  font-size: 12px; color: var(--text-secondary, #aaa);
}
.step-list { display: flex; flex-direction: column; gap: 6px; }
.step-row { display: flex; align-items: center; gap: 6px; }
.step-num {
  font-size: 11px; color: var(--text-muted, #777);
  width: 14px; text-align: center; flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.step-input {
  flex: 1; min-width: 0;
  padding: 4px 10px; border-radius: 8px;
  font-size: 12px;
  color: var(--text-primary, #eee);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  background: var(--bg-input, rgba(0, 0, 0, 0.2));
  outline: none;
}
.step-input:focus { border-color: rgba(59, 130, 246, 0.5); }
.step-del {
  flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 6px;
  color: var(--text-muted, #777);
  border: none; background: transparent; cursor: pointer;
}
.step-del:hover:not(:disabled) { color: #f87171; background: rgba(248, 113, 113, 0.1); }
.step-del:disabled { opacity: 0.3; cursor: not-allowed; }
.add-step {
  align-self: flex-start;
  font-size: 12px; padding: 2px 8px; border-radius: 8px;
  color: var(--brand-blue, #3b82f6);
  border: 1px dashed rgba(59, 130, 246, 0.4);
  background: transparent; cursor: pointer;
}
.add-step:hover { background: rgba(59, 130, 246, 0.08); }
.card-steps { display: flex; flex-wrap: wrap; gap: 6px; }
.card-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 999px;
  font-size: 12px; color: var(--text-secondary, #aaa);
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  background: var(--bg-elevated, rgba(255, 255, 255, 0.04));
  max-width: 280px;
}
.chip-num { font-size: 11px; color: var(--text-muted, #777); font-variant-numeric: tabular-nums; }
.chip-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-actions { display: flex; gap: 8px; margin-top: 2px; }
.btn-run {
  font-size: 12px; font-weight: 600;
  padding: 4px 18px; border-radius: 8px;
  color: #fff; border: none; cursor: pointer;
  background: var(--brand-blue, #3b82f6);
}
.btn-run:hover:not(:disabled) { filter: brightness(1.1); }
.btn-run:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-cancel {
  font-size: 12px;
  padding: 4px 14px; border-radius: 8px;
  color: var(--text-secondary, #aaa); cursor: pointer;
  border: 1px solid var(--border-soft, rgba(255, 255, 255, 0.08));
  background: transparent;
}
.btn-cancel:hover { color: var(--text-primary, #eee); }
</style>
