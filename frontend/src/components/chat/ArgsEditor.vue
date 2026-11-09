<script setup lang="ts">
// 按工具的参数结构（JSON Schema）生成编辑表单：策略用下拉选择，数字用数字框，复杂参数用 JSON 文本。
import { NInput, NInputNumber, NSelect, NSwitch, NTooltip } from 'naive-ui'
import { computed, reactive } from 'vue'
import { useAgentControl } from '@/stores/agentControl'
import { useCatalog } from '@/stores/catalog'

const props = defineProps<{ tool: string }>()
const args = defineModel<Record<string, any>>({ required: true })
const store = useAgentControl()
const catalog = useCatalog()

const schema = computed(() => store.toolMeta(props.tool)?.parameters ?? { properties: {}, required: [] })
const required = computed(() => new Set(schema.value.required ?? []))
const keys = computed(() => [...new Set([...Object.keys(schema.value.properties ?? {}), ...Object.keys(args.value)])])
const jsonText = reactive<Record<string, string>>({})
const jsonErr = reactive<Record<string, boolean>>({})

const STRATEGY_KEYS = new Set(['strategy', 'base'])
const strategyOptions = computed(() => {
  const allowed = store.control.strategies
  return catalog.strategies.filter((s) => !allowed || allowed.includes(s.id)).map((s) => ({ label: `${s.name}（${s.id}）`, value: s.id }))
})

function kind(k: string): 'strategy' | 'enum' | 'number' | 'boolean' | 'json' | 'string' {
  const p = schema.value.properties?.[k] ?? {}
  const v = args.value[k]
  if (STRATEGY_KEYS.has(k)) return 'strategy'
  if (p.enum) return 'enum'
  if (p.type === 'number' || p.type === 'integer' || typeof v === 'number') return 'number'
  if (p.type === 'boolean' || typeof v === 'boolean') return 'boolean'
  if (p.type === 'object' || p.type === 'array' || (v !== null && typeof v === 'object')) return 'json'
  return 'string'
}
function set(k: string, v: any) {
  const next = { ...args.value }
  if (v === null || v === undefined || v === '') delete next[k]
  else next[k] = v
  args.value = next
}
function jsonValue(k: string) {
  if (!(k in jsonText)) jsonText[k] = args.value[k] === undefined ? '' : JSON.stringify(args.value[k], null, 1)
  return jsonText[k]
}
function onJson(k: string, text: string) {
  jsonText[k] = text
  if (!text.trim()) { jsonErr[k] = false; return set(k, undefined) }
  try {
    set(k, JSON.parse(text))
    jsonErr[k] = false
  } catch {
    jsonErr[k] = true
  }
}
const desc = (k: string) => schema.value.properties?.[k]?.description ?? ''
const enumOpts = (k: string) => (schema.value.properties?.[k]?.enum ?? []).map((v: string) => ({ label: v, value: v }))
</script>

<template>
  <div class="args">
    <div v-for="k in keys" :key="k" class="field">
      <NTooltip :disabled="!desc(k)" placement="top-start">
        <template #trigger>
          <label :class="{ req: required.has(k) }">{{ k }}</label>
        </template>
        {{ desc(k) }}
      </NTooltip>
      <NSelect v-if="kind(k) === 'strategy'" :value="args[k]" size="small" filterable tag :options="strategyOptions"
        placeholder="选择策略" @update:value="(v: any) => set(k, v)" />
      <NSelect v-else-if="kind(k) === 'enum'" :value="args[k]" size="small" clearable :options="enumOpts(k)" @update:value="(v: any) => set(k, v)" />
      <NInputNumber v-else-if="kind(k) === 'number'" :value="args[k]" size="small" clearable @update:value="(v: any) => set(k, v)" />
      <NSwitch v-else-if="kind(k) === 'boolean'" :value="!!args[k]" size="small" @update:value="(v: any) => set(k, v)" />
      <NInput v-else-if="kind(k) === 'json'" :value="jsonValue(k)" type="textarea" size="small" :autosize="{ minRows: 1, maxRows: 6 }"
        :status="jsonErr[k] ? 'error' : undefined" class="mono" placeholder="JSON，如 {&quot;atr_period&quot;: 22}" @update:value="(v: string) => onJson(k, v)" />
      <NInput v-else :value="args[k] ?? ''" size="small" clearable :placeholder="k === 'start' || k === 'end' ? 'YYYY-MM-DD' : ''"
        @update:value="(v: string) => set(k, v)" />
    </div>
    <div v-if="!keys.length" class="none">这个工具没有参数</div>
  </div>
</template>

<style scoped>
.args { display: grid; gap: 6px; padding: 8px 10px; border-radius: 9px; background: var(--surface-2); border: 1px dashed var(--border); }
.field { display: grid; grid-template-columns: 120px 1fr; align-items: center; gap: 8px; }
label { font-family: var(--mono); font-size: 12px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: help; }
label.req::after { content: " *"; color: var(--up); }
.mono :deep(textarea) { font-family: var(--mono); font-size: 12px; }
.none { font-size: 12px; color: var(--text-3); }
@media (max-width: 640px) { .field { grid-template-columns: 1fr; gap: 2px; } }
</style>
