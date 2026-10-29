<script setup lang="ts">
// 回测设置：区间、初始资金、交易成本、基准
import { NCheckbox, NCheckboxGroup, NCollapseTransition, NDatePicker, NInputNumber } from 'naive-ui'
import { ChevronDown } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import type { BacktestConfig } from '@/api/client'
import { useCatalog } from '@/stores/catalog'

const props = defineProps<{ modelValue: BacktestConfig; category?: string }>()
const emit = defineEmits<{ 'update:modelValue': [BacktestConfig] }>()
const catalog = useCatalog()
const showCosts = ref(false)

function set<K extends keyof BacktestConfig>(k: K, v: BacktestConfig[K]) {
  emit('update:modelValue', { ...props.modelValue, [k]: v })
}
const toTs = (s: string) => new Date(s + 'T00:00:00').getTime()
const toStr = (t: number) => {
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const range = computed<[number, number]>(() => [toTs(props.modelValue.start), toTs(props.modelValue.end)])
function setRange(v: [number, number] | null) {
  if (!v) return
  emit('update:modelValue', { ...props.modelValue, start: toStr(v[0]), end: toStr(v[1]) })
}
const dataEnd = computed(() => {
  const r = catalog.market?.ranges
  const k = props.category === 'futures' ? 'futures' : 'stock'
  return r?.[k]?.[1] ?? '2026-10-28'
})
const dataStart = computed(() => catalog.market?.ranges?.[props.category === 'futures' ? 'futures' : 'stock']?.[0] ?? '2016-01-04')
const shortcuts = computed(() => {
  const end = toTs(dataEnd.value)
  const yearsAgo = (n: number) => end - n * 365.25 * 86400000
  return {
    '近 1 年': [yearsAgo(1), end] as [number, number],
    '近 3 年': [yearsAgo(3), end] as [number, number],
    '近 5 年': [yearsAgo(5), end] as [number, number],
    '2022—2025': [toTs('2022-01-01'), toTs('2025-12-31')] as [number, number],
    '2021—2024': [toTs('2021-01-01'), toTs('2024-12-31')] as [number, number],
  }
})
const disabled = (ts: number) => ts < toTs(dataStart.value) || ts > toTs(dataEnd.value)
const capitalWan = computed(() => (props.modelValue.initial_capital ?? 1e7) / 1e4)
</script>

<template>
  <div class="cfg">
    <label class="lbl">回测区间 <span class="muted">数据范围 {{ dataStart }} ~ {{ dataEnd }}</span></label>
    <NDatePicker type="daterange" :value="range" :shortcuts="shortcuts" :is-date-disabled="disabled" size="small" @update:value="setRange" />

    <label class="lbl">初始资金</label>
    <NInputNumber :value="capitalWan" :min="1" :max="1000000" :step="100" size="small" @update:value="(v) => set('initial_capital', (v ?? 1000) * 1e4)">
      <template #suffix>万元</template>
    </NInputNumber>

    <label class="lbl">对比基准</label>
    <NCheckboxGroup :value="modelValue.benchmarks ?? ['000300', '000905', '399006']" @update:value="(v) => set('benchmarks', v as string[])">
      <div class="benches">
        <NCheckbox v-for="b in catalog.market?.benchmarks ?? []" :key="b.code" :value="b.code" :label="b.name" />
      </div>
    </NCheckboxGroup>

    <button class="toggle" @click="showCosts = !showCosts">
      交易成本与风控 <ChevronDown :size="14" :class="{ up: showCosts }" />
    </button>
    <NCollapseTransition :show="showCosts">
      <div class="costs">
        <div class="ci"><span>股票佣金率</span><NInputNumber :value="(modelValue.stock_commission ?? 0.00025) * 1e4" :min="0" :max="100" :step="0.5" size="small" @update:value="(v) => set('stock_commission', (v ?? 2.5) / 1e4)"><template #suffix>‱</template></NInputNumber></div>
        <div class="ci"><span>股票滑点</span><NInputNumber :value="(modelValue.stock_slippage ?? 0.0005) * 1e4" :min="0" :max="500" :step="1" size="small" @update:value="(v) => set('stock_slippage', (v ?? 5) / 1e4)"><template #suffix>‱</template></NInputNumber></div>
        <div class="ci"><span>期货滑点</span><NInputNumber :value="modelValue.futures_slippage_ticks ?? 1" :min="0" :max="20" :step="1" size="small" @update:value="(v) => set('futures_slippage_ticks', v ?? 1)"><template #suffix>跳</template></NInputNumber></div>
        <div class="ci"><span>期货手续费倍数</span><NInputNumber :value="modelValue.futures_commission_scale ?? 1" :min="0" :max="10" :step="0.5" size="small" @update:value="(v) => set('futures_commission_scale', v ?? 1)"><template #suffix>倍</template></NInputNumber></div>
        <div class="ci"><span>保证金占用上限</span><NInputNumber :value="(modelValue.max_margin_ratio ?? 0.8) * 100" :min="5" :max="100" :step="5" size="small" @update:value="(v) => set('max_margin_ratio', (v ?? 80) / 100)"><template #suffix>%</template></NInputNumber></div>
        <div class="ci"><span>无风险利率</span><NInputNumber :value="(modelValue.risk_free_rate ?? 0) * 100" :min="0" :max="20" :step="0.25" size="small" @update:value="(v) => set('risk_free_rate', (v ?? 0) / 100)"><template #suffix>%</template></NInputNumber></div>
        <p class="muted note">印花税按日期自动计算（2023-08-28 前 0.1%，之后 0.05%，仅卖出收取）；股票单笔最低佣金 5 元</p>
      </div>
    </NCollapseTransition>
  </div>
</template>

<style scoped>
.cfg { display: flex; flex-direction: column; gap: 6px; }
.lbl { font-size: 12.5px; font-weight: 550; color: var(--text-2); margin-top: 8px; display: flex; justify-content: space-between; gap: 8px; }
.lbl .muted { font-weight: 400; font-size: 11.5px; }
.benches { display: flex; gap: 12px; flex-wrap: wrap; }
.toggle { margin-top: 10px; border: none; background: none; padding: 0; color: var(--text-2); font-size: 12.5px; font-weight: 550; cursor: pointer; display: flex; align-items: center; gap: 4px; font-family: inherit; }
.toggle svg { transition: transform 0.15s; }
.toggle svg.up { transform: rotate(180deg); }
.costs { display: flex; flex-direction: column; gap: 6px; padding-top: 6px; }
.ci { display: grid; grid-template-columns: 1fr 130px; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-2); }
.note { font-size: 11.5px; margin: 4px 0 0; line-height: 1.5; }
</style>
