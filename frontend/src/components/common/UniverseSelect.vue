<script setup lang="ts">
// 标的池选择：预设池，或从股票 / 行业 / 期货列表中自选
import { NRadioButton, NRadioGroup, NSelect } from 'naive-ui'
import { computed } from 'vue'
import { useCatalog } from '@/stores/catalog'

const props = defineProps<{ modelValue: string; assetTypes: string[]; defaultUniverse: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const catalog = useCatalog()

const PRESETS: Record<string, string> = { stock_pool: 'stock', industries: 'industry', futures: 'futures' }
const presets = computed(() => (catalog.market?.universe_presets ?? []).filter((p) => props.assetTypes.includes(PRESETS[p.value])))
const isPreset = computed(() => props.modelValue in PRESETS)
const mode = computed(() => (isPreset.value ? 'preset' : 'custom'))

const options = computed(() => {
  const m = catalog.market
  if (!m) return []
  const groups = []
  if (props.assetTypes.includes('stock')) groups.push({ type: 'group', label: '股票', key: 's', children: m.stocks.map((s) => ({ label: `${s.name} ${s.symbol} · ${s.industry}`, value: s.symbol })) })
  if (props.assetTypes.includes('industry')) groups.push({ type: 'group', label: '申万一级行业', key: 'i', children: m.industries.map((s) => ({ label: `${s.name} ${s.symbol}`, value: s.symbol })) })
  if (props.assetTypes.includes('futures')) groups.push({ type: 'group', label: '商品期货', key: 'f', children: m.futures.map((s) => ({ label: `${s.name} ${s.symbol} · ${s.sector}`, value: s.symbol })) })
  return groups
})
const selected = computed(() => (isPreset.value ? [] : props.modelValue.split(',').filter(Boolean)))

function setMode(m: string) {
  if (m === 'preset') emit('update:modelValue', presets.value.find((p) => p.value === props.defaultUniverse)?.value ?? presets.value[0]?.value ?? props.defaultUniverse)
  else emit('update:modelValue', isPreset.value ? '' : props.modelValue)
}
</script>

<template>
  <div class="uni">
    <NRadioGroup :value="mode" size="small" @update:value="setMode">
      <NRadioButton value="preset" :disabled="!presets.length">预设标的池</NRadioButton>
      <NRadioButton value="custom">自选标的</NRadioButton>
    </NRadioGroup>
    <NSelect v-if="mode === 'preset'" :value="modelValue" :options="presets" size="small" @update:value="(v) => emit('update:modelValue', v)" />
    <NSelect
      v-else multiple filterable clearable max-tag-count="responsive" size="small" placeholder="搜索名称或代码，可多选"
      :value="selected" :options="options as any" @update:value="(v: string[]) => emit('update:modelValue', v.join(','))"
    />
  </div>
</template>

<style scoped>
.uni { display: flex; flex-direction: column; gap: 6px; }
</style>
