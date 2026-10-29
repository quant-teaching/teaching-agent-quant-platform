<script setup lang="ts">
// 根据策略的参数定义自动生成表单。修改过的参数会高亮，并可一键恢复默认
import { RotateCcw } from 'lucide-vue-next'
import { NInputNumber, NInput, NSelect, NSwitch, NTooltip } from 'naive-ui'
import type { ParamSpec } from '@/api/client'
import { paramValue } from '@/utils/format'

const props = defineProps<{ specs: ParamSpec[]; modelValue: Record<string, any>; dense?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [Record<string, any>] }>()

function set(key: string, v: any) {
  emit('update:modelValue', { ...props.modelValue, [key]: v })
}
function step(p: ParamSpec) {
  if (p.type === 'integer') return 1
  const ref = Math.abs(p.default ?? 1)
  if (ref === 0) return 0.01
  return ref < 0.01 ? 0.001 : ref < 0.1 ? 0.005 : ref < 1 ? 0.05 : ref < 10 ? 0.1 : 1
}
function changed(p: ParamSpec) {
  return props.modelValue[p.key] !== undefined && props.modelValue[p.key] !== p.default
}
function range(p: ParamSpec) {
  const lo = p.min ?? p.gt
  const hi = p.max ?? p.lt
  if (lo === undefined && hi === undefined) return ''
  return `${lo ?? '-∞'} ~ ${hi ?? '∞'}`
}
const OPTION_LABELS: Record<string, string> = {
  breakout: '突破', reversion: '回归', reverse: '反手', middle: '中线离场',
  W: '每周', M: '每月', Q: '每季度', SMA: '简单平均 SMA', EMA: '指数平均 EMA',
}
</script>

<template>
  <div class="form" :class="{ dense }">
    <div v-for="p in specs" :key="p.key" class="row" :class="{ changed: changed(p) }">
      <div class="label">
        <NTooltip placement="top-start" :style="{ maxWidth: '320px' }">
          <template #trigger>
            <span class="title">{{ p.title }}</span>
          </template>
          {{ p.description }}
        </NTooltip>
        <span class="key">{{ p.key }}</span>
        <button v-if="changed(p)" class="reset" :title="`恢复默认值 ${paramValue(p.default)}`" @click="set(p.key, p.default)">
          <RotateCcw :size="12" />
        </button>
      </div>
      <div class="control">
        <NSwitch v-if="p.type === 'boolean'" :value="modelValue[p.key] ?? p.default" @update:value="(v) => set(p.key, v)" />
        <NSelect
          v-else-if="p.options"
          size="small"
          :value="modelValue[p.key] ?? p.default"
          :options="p.options.map((o) => ({ label: OPTION_LABELS[o] ?? o, value: o }))"
          @update:value="(v) => set(p.key, v)"
        />
        <NInputNumber
          v-else-if="p.type === 'integer' || p.type === 'number'"
          size="small"
          :value="modelValue[p.key] ?? p.default"
          :min="p.min ?? p.gt"
          :max="p.max ?? p.lt"
          :step="step(p)"
          :precision="p.type === 'integer' ? 0 : undefined"
          @update:value="(v) => set(p.key, v ?? p.default)"
        />
        <NInput v-else size="small" :value="modelValue[p.key] ?? p.default" @update:value="(v) => set(p.key, v)" />
      </div>
      <div v-if="!dense" class="desc">{{ p.description }}<span v-if="range(p)" class="range">范围 {{ range(p) }} · 默认 {{ paramValue(p.default) }}</span></div>
    </div>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 4px; }
.row { display: grid; grid-template-columns: minmax(150px, 210px) minmax(140px, 220px) 1fr; align-items: center; gap: 4px 16px; padding: 9px 10px; border-radius: 10px; }
.row.changed { background: var(--primary-soft); }
.dense .row { grid-template-columns: minmax(0, 1fr) 150px; padding: 6px 8px; }
.dense .key { display: none; }
.title { white-space: nowrap; }
.label { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
.title { font-size: 13.5px; font-weight: 550; color: var(--text-1); cursor: help; border-bottom: 1px dotted var(--border-strong); }
.key { font-family: var(--mono); font-size: 11px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reset { border: none; background: none; color: var(--primary); cursor: pointer; padding: 0 2px; display: inline-flex; }
.control :deep(.n-input-number), .control :deep(.n-select) { width: 100%; }
.desc { font-size: 12.5px; color: var(--text-3); line-height: 1.5; }
.range { margin-left: 8px; color: var(--text-3); opacity: 0.85; white-space: nowrap; }
@media (max-width: 1000px) { .row { grid-template-columns: 1fr 1fr; } .desc { grid-column: 1 / -1; } }
</style>
