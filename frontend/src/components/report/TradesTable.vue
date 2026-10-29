<script setup lang="ts">
import { NDataTable, NRadioButton, NRadioGroup, type DataTableColumns } from 'naive-ui'
import { computed, h, ref } from 'vue'
import type { Fill, Trade } from '@/api/client'
import { int, num, pct, signClass } from '@/utils/format'

const props = defineProps<{ trades: Trade[]; fills: Fill[]; fillsTruncated?: boolean; fillTotal?: number }>()
const view = ref<'trades' | 'fills'>('trades')

const tradeCols: DataTableColumns<Trade> = [
  { title: '标的', key: 'name', width: 110, fixed: 'left', render: (r) => h('span', [r.name, h('span', { class: 'muted', style: 'margin-left:6px;font-size:12px' }, r.symbol)]) },
  { title: '方向', key: 'side', width: 60, render: (r) => h('span', { class: 'tag-soft' }, r.side) },
  { title: '开仓日', key: 'entry_date', width: 104, sorter: (a, b) => a.entry_date.localeCompare(b.entry_date) },
  { title: '平仓日', key: 'exit_date', width: 104, render: (r) => (r.is_open ? h('span', { class: 'muted' }, '持仓中') : r.exit_date) },
  { title: '持仓天数', key: 'holding_days', width: 86, align: 'right', sorter: (a, b) => a.holding_days - b.holding_days },
  { title: '开仓均价', key: 'entry_price', width: 96, align: 'right', render: (r) => num(r.entry_price) },
  { title: '平仓均价', key: 'exit_price', width: 96, align: 'right', render: (r) => num(r.exit_price) },
  { title: '收益率', key: 'return_pct', width: 90, align: 'right', sorter: (a, b) => a.return_pct - b.return_pct, render: (r) => h('span', { class: 'num ' + signClass(r.return_pct) }, pct(r.return_pct, 2, true)) },
  { title: '净盈亏(元)', key: 'pnl', width: 110, align: 'right', sorter: (a, b) => a.pnl - b.pnl, render: (r) => h('span', { class: 'num ' + signClass(r.pnl) }, int(r.pnl)) },
  { title: '手续费(元)', key: 'cost', width: 96, align: 'right', render: (r) => int(r.cost) },
]

const fillCols: DataTableColumns<Fill> = [
  { title: '日期', key: 'date', width: 104, fixed: 'left' },
  { title: '标的', key: 'name', width: 110, render: (r) => h('span', [r.name, r.contract && r.contract !== r.symbol ? h('span', { class: 'muted', style: 'margin-left:6px;font-size:12px' }, r.contract) : null]) },
  { title: '操作', key: 'action', width: 110, render: (r) => h('span', { class: 'tag-soft' }, r.action) },
  { title: '数量', key: 'qty', width: 90, align: 'right', render: (r) => int(Math.abs(r.qty)) },
  { title: '成交价', key: 'price', width: 96, align: 'right', render: (r) => num(r.price) },
  { title: '成交金额(元)', key: 'amount', width: 120, align: 'right', render: (r) => int(r.amount) },
  { title: '手续费', key: 'fee', width: 86, align: 'right', render: (r) => num(r.fee) },
  { title: '滑点成本', key: 'slippage', width: 86, align: 'right', render: (r) => num(r.slippage) },
  { title: '备注', key: 'note', minWidth: 120, ellipsis: { tooltip: true } },
]

const pagination = { pageSize: 15, showSizePicker: true, pageSizes: [15, 30, 50, 100] }
const tradeRows = computed(() => [...props.trades].reverse())
</script>

<template>
  <div>
    <div class="bar">
      <NRadioGroup v-model:value="view" size="small">
        <NRadioButton value="trades">完整交易（{{ trades.length }}）</NRadioButton>
        <NRadioButton value="fills">逐笔成交（{{ fillTotal ?? fills.length }}）</NRadioButton>
      </NRadioGroup>
      <span class="muted hint">
        <template v-if="view === 'trades'">一笔完整交易 = 一个标的从开仓到完全平仓；净盈亏已扣除手续费，成交价已含滑点</template>
        <template v-else>信号在前一日收盘生成、当日开盘成交{{ fillsTruncated ? '；仅显示前 5000 笔' : '' }}</template>
      </span>
    </div>
    <NDataTable v-if="view === 'trades'" :columns="tradeCols" :data="tradeRows" :pagination="pagination" size="small" :scroll-x="980" :bordered="false" striped />
    <NDataTable v-else :columns="fillCols" :data="fills" :pagination="pagination" size="small" :scroll-x="1000" :bordered="false" striped />
  </div>
</template>

<style scoped>
.bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.hint { font-size: 12px; }
</style>
