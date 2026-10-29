<script setup lang="ts">
// 九项核心量化指标。收益类数字红涨绿跌；每项下方给出沪深 300 同口径对比，悬停显示指标含义
import { NTooltip } from 'naive-ui'
import { computed } from 'vue'
import type { BacktestPayload } from '@/api/client'
import { num, pct, signClass } from '@/utils/format'

const props = withDefaults(defineProps<{ data: BacktestPayload; columns?: number }>(), { columns: 5 })

const tiles = computed(() => {
  const m = props.data.metrics
  const b = props.data.benchmarks['000300']
  const plr = m.profit_loss_ratio
  return [
    { label: '总收益率', value: pct(m.total_return, 1, true), cls: signClass(m.total_return), sub: b ? `沪深300 ${pct(b.total_return, 1, true)}` : '', tip: '期末净值 / 期初净值 - 1' },
    { label: '年化收益率', value: pct(m.annual_return, 1, true), cls: signClass(m.annual_return), sub: b ? `沪深300 ${pct(b.annual_return, 1, true)}` : '', tip: '复合年增长率：(期末/期初)^(252/交易日数) - 1' },
    { label: '最大回撤', value: pct(m.max_drawdown, 1), cls: 'down-dd', sub: b ? `沪深300 ${pct(b.max_drawdown, 1)}` : '', tip: '净值从历史高点下跌的最大幅度，衡量最坏情况' },
    { label: '夏普比率', value: num(m.sharpe), cls: '', sub: b ? `沪深300 ${num(b.sharpe)}` : '', tip: '每承担一单位波动获得的超额收益（年化）' },
    { label: '卡玛比率', value: num(m.calmar), cls: '', sub: b ? `沪深300 ${num(b.calmar)}` : '', tip: '年化收益率 / |最大回撤|' },
    { label: '年化波动率', value: pct(m.volatility, 1), cls: '', sub: b ? `沪深300 ${pct(b.volatility, 1)}` : '', tip: '日收益率标准差 × √252' },
    { label: '胜率', value: pct(m.win_rate, 1), cls: '', sub: `${m.trade_count} 笔已平仓`, tip: '盈利交易笔数 / 已平仓交易笔数' },
    { label: '盈亏比', value: plr === null ? (m.trade_count ? '∞' : '—') : num(plr), cls: '', sub: `利润因子 ${num(m.profit_factor)}`, tip: '平均盈利 / |平均亏损|' },
    { label: '交易次数', value: String(m.trade_count), cls: '', sub: `成交 ${m.fill_count} 笔`, tip: '完整交易（开仓到平仓）的笔数；成交笔数含加减仓与移仓' },
    { label: '交易成本', value: pct(m.cost_ratio, 2), cls: '', sub: `年化换手 ${num(m.annual_turnover, 1)} 倍`, tip: '累计手续费、印花税与滑点 / 初始资金' },
  ]
})
</script>

<template>
  <div class="tiles" :style="{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }">
    <NTooltip v-for="t in tiles" :key="t.label" placement="top" :delay="300">
      <template #trigger>
        <div class="tile">
          <div class="label">{{ t.label }}</div>
          <div class="value num" :class="t.cls === 'down-dd' ? 'dd' : t.cls">{{ t.value }}</div>
          <div class="sub num">{{ t.sub }}</div>
        </div>
      </template>
      {{ t.tip }}
    </NTooltip>
  </div>
</template>

<style scoped>
.tiles { display: grid; gap: 10px; }
.tile {
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px;
  padding: 11px 14px 10px; cursor: default; transition: border-color 0.15s;
}
.tile:hover { border-color: var(--border-strong); }
.label { font-size: 12px; color: var(--text-3); }
.value { font-size: 21px; font-weight: 650; line-height: 1.35; margin-top: 2px; letter-spacing: 0.2px; }
.value.dd { color: var(--text-1); }
.sub { font-size: 11.5px; color: var(--text-3); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 1100px) { .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; } }
@media (max-width: 600px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; } }
</style>
