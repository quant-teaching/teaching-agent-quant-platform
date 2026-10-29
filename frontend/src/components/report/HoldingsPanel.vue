<script setup lang="ts">
// 任意交易日的持仓明细：日期选择 + 前后交易日切换
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { NButton, NDataTable, NDatePicker, NEmpty, NSpin, type DataTableColumns } from 'naive-ui'
import { computed, h, ref, watch } from 'vue'
import { getHoldings, type Holding } from '@/api/client'
import { int, money, num, pct } from '@/utils/format'

const props = defineProps<{ resultId: string; dates: string[]; futures?: boolean }>()
const date = defineModel<string>('date', { required: true })

const rows = ref<Holding[]>([])
const loading = ref(false)
const error = ref('')
const actual = ref('')

const dateSet = computed(() => new Set(props.dates))
const idx = computed(() => props.dates.indexOf(date.value))
const fmt = (ts: number) => {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const step = (k: number) => {
  const i = Math.min(props.dates.length - 1, Math.max(1, idx.value + k))
  date.value = props.dates[i]
}

let seq = 0
watch(
  () => [props.resultId, date.value],
  async () => {
    const my = ++seq
    loading.value = true
    error.value = ''
    try {
      const data = await getHoldings(props.resultId, date.value)
      if (my !== seq) return
      rows.value = [...data].sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
      actual.value = data[0]?.date ?? ''
    } catch (e: any) {
      if (my === seq) error.value = e.message
    } finally {
      if (my === seq) loading.value = false
    }
  },
  { immediate: true },
)

const long = computed(() => rows.value.filter((r) => r.weight > 0).reduce((s, r) => s + r.weight, 0))
const short = computed(() => rows.value.filter((r) => r.weight < 0).reduce((s, r) => s + r.weight, 0))
const maxW = computed(() => Math.max(0.0001, ...rows.value.map((r) => Math.abs(r.weight))))

const cols = computed<DataTableColumns<Holding>>(() => [
  { title: '标的', key: 'name', width: 130, render: (r) => h('span', [r.name, h('span', { class: 'muted', style: 'margin-left:6px;font-size:12px' }, r.symbol)]) },
  ...(props.futures ? [{ title: '合约', key: 'contract', width: 86 } as const] : []),
  { title: '方向', key: 'dir', width: 60, render: (r) => h('span', { class: 'tag-soft' }, r.qty < 0 ? '空' : '多') },
  { title: props.futures ? '手数' : '股数', key: 'qty', width: 90, align: 'right', render: (r) => int(Math.abs(r.qty)) },
  { title: '收盘价', key: 'price', width: 90, align: 'right', render: (r) => num(r.price) },
  { title: props.futures ? '名义市值' : '市值', key: 'value', width: 100, align: 'right', render: (r) => money(Math.abs(r.value)) },
  {
    title: '占权益比例', key: 'weight', minWidth: 160,
    render: (r) => h('div', { class: 'wcell' }, [
      h('div', { class: 'wbar' }, [h('i', { class: r.weight < 0 ? 'neg' : '', style: { width: `${(Math.abs(r.weight) / maxW.value) * 100}%` } })]),
      h('span', { class: 'num' }, pct(r.weight, 1)),
    ]),
  },
])
</script>

<template>
  <div class="hp">
    <div class="bar">
      <NButton size="small" quaternary :disabled="idx <= 1" title="上一个交易日" @click="step(-1)"><ChevronLeft :size="16" /></NButton>
      <NDatePicker
        v-model:formatted-value="date" value-format="yyyy-MM-dd" type="date" size="small" style="width: 150px"
        :is-date-disabled="(ts: number) => !dateSet.has(fmt(ts))" :actions="null"
      />
      <NButton size="small" quaternary :disabled="idx < 0 || idx >= dates.length - 1" title="下一个交易日" @click="step(1)"><ChevronRight :size="16" /></NButton>
      <span v-if="rows.length" class="muted sum">
        {{ rows.length }} 个标的 · 多头 {{ pct(long, 1) }}<template v-if="short < 0"> · 空头 {{ pct(short, 1) }}</template>
      </span>
    </div>
    <p class="muted note">
      收盘后的持仓；比例 = 市值 / 当日总权益{{ futures ? '，期货按名义市值计算，可以超过 100%（杠杆）' : '' }}。
      <template v-if="actual && actual !== date">{{ date }} 不是交易日，显示 {{ actual }} 的持仓。</template>
    </p>
    <NSpin :show="loading">
      <div v-if="error" class="muted">{{ error }}</div>
      <NEmpty v-else-if="!rows.length && !loading" description="当日空仓" size="small" style="padding: 24px 0" />
      <NDataTable v-else :columns="cols" :data="rows" size="small" :bordered="false" :max-height="420" :scroll-x="futures ? 720 : 640" />
    </NSpin>
  </div>
</template>

<style scoped>
.bar { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.sum { margin-left: 10px; font-size: 12.5px; }
.note { font-size: 12px; margin: 6px 0 10px; }
:deep(.wcell) { display: flex; align-items: center; gap: 8px; }
:deep(.wbar) { flex: 1; height: 6px; border-radius: 3px; background: var(--surface-3); overflow: hidden; min-width: 50px; max-width: 220px; }
:deep(.wbar i) { display: block; height: 100%; border-radius: 3px; background: var(--primary); }
:deep(.wbar i.neg) { background: var(--text-3); }
:deep(.wcell .num) { width: 52px; text-align: right; }
</style>
