<script setup lang="ts">
// 九项核心量化指标。收益类数字红涨绿跌；每项下方给出沪深 300 同口径对比，悬停显示指标含义
import { Activity, CalendarRange, Gauge, Percent, Receipt, Repeat, Scale, Target, TrendingDown, TrendingUp } from 'lucide-vue-next'
import { NTooltip } from 'naive-ui'
import { computed } from 'vue'
import CountUp from '@/components/common/CountUp.vue'
import type { BacktestPayload } from '@/api/client'
import { num, pct, signClass } from '@/utils/format'

const props = withDefaults(defineProps<{ data: BacktestPayload; columns?: number }>(), { columns: 5 })

const tiles = computed(() => {
  const m = props.data.metrics
  const b = props.data.benchmarks['000300']
  const plr = m.profit_loss_ratio
  return [
    { icon: TrendingUp, tone: 'blue', label: '总收益率', value: pct(m.total_return, 1, true), cls: signClass(m.total_return), sub: b ? `沪深300 ${pct(b.total_return, 1, true)}` : '', tip: '期末净值 / 期初净值 - 1' },
    { icon: CalendarRange, tone: 'blue', label: '年化收益率', value: pct(m.annual_return, 1, true), cls: signClass(m.annual_return), sub: b ? `沪深300 ${pct(b.annual_return, 1, true)}` : '', tip: '复合年增长率：(期末/期初)^(252/交易日数) - 1' },
    { icon: TrendingDown, tone: 'rose', label: '最大回撤', value: pct(m.max_drawdown, 1), cls: 'down-dd', sub: b ? `沪深300 ${pct(b.max_drawdown, 1)}` : '', tip: '净值从历史高点下跌的最大幅度，衡量最坏情况' },
    { icon: Gauge, tone: 'violet', label: '夏普比率', value: num(m.sharpe), cls: '', sub: b ? `沪深300 ${num(b.sharpe)}` : '', tip: '每承担一单位波动获得的超额收益（年化）' },
    { icon: Scale, tone: 'violet', label: '卡玛比率', value: num(m.calmar), cls: '', sub: b ? `沪深300 ${num(b.calmar)}` : '', tip: '年化收益率 / |最大回撤|' },
    { icon: Activity, tone: 'amber', label: '年化波动率', value: pct(m.volatility, 1), cls: '', sub: b ? `沪深300 ${pct(b.volatility, 1)}` : '', tip: '日收益率标准差 × √252' },
    { icon: Target, tone: 'teal', label: '胜率', value: pct(m.win_rate, 1), cls: '', sub: `${m.trade_count} 笔已平仓`, tip: '盈利交易笔数 / 已平仓交易笔数' },
    { icon: Percent, tone: 'teal', label: '盈亏比', value: plr === null ? (m.trade_count ? '∞' : '—') : num(plr), cls: '', sub: `利润因子 ${m.profit_factor === null ? (m.trade_count ? '∞' : '—') : num(m.profit_factor)}`, tip: '平均盈利 / |平均亏损|' },
    { icon: Repeat, tone: 'amber', label: '交易次数', value: String(m.trade_count), cls: '', sub: `成交 ${m.fill_count} 笔`, tip: '完整交易（开仓到平仓）的笔数；成交笔数含加减仓与移仓' },
    { icon: Receipt, tone: 'rose', label: '交易成本', value: pct(m.cost_ratio, 2), cls: '', sub: `年化换手 ${num(m.annual_turnover, 1)} 倍`, tip: '累计手续费、印花税与滑点 / 初始资金' },
  ]
})
</script>

<template>
  <div class="tiles stagger" :style="{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }">
    <NTooltip v-for="t in tiles" :key="t.label" placement="top" :delay="300">
      <template #trigger>
        <div class="tile" :class="`tone-${t.tone}`">
          <div class="label"><span class="mini"><component :is="t.icon" :size="13" :stroke-width="2.2" /></span>{{ t.label }}</div>
          <div class="value num" :class="t.cls === 'down-dd' ? 'dd' : t.cls"><CountUp :value="t.value" /></div>
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
  padding: 11px 14px 10px; cursor: default; position: relative; overflow: hidden;
  transition: border-color 0.2s, transform 0.25s var(--ease-out), box-shadow 0.25s var(--ease-out);
}
.tile::before {
  content: ""; position: absolute; inset: 0 0 auto; height: 2px; background: var(--brand-grad);
  transform: scaleX(0); transform-origin: left; transition: transform 0.35s var(--ease-out);
}
.tile:hover { border-color: var(--border-strong); transform: translateY(-2px); box-shadow: var(--shadow-md); }
.tile:hover::before { transform: scaleX(1); }
.label { font-size: 12px; color: var(--text-3); display: flex; align-items: center; gap: 7px; }
.mini { width: 22px; height: 22px; border-radius: 7px; display: grid; place-items: center; color: var(--tone); background: var(--tone-soft); transition: transform 0.35s var(--ease-spring); }
.tile:hover .mini { transform: scale(1.12) rotate(-8deg); }
.tile::before { background: var(--tone) !important; }
.tile { background: linear-gradient(160deg, var(--surface-2) 55%, color-mix(in srgb, var(--tone-soft) 60%, var(--surface-2))) !important; }
.value { margin-top: 4px !important; font-size: 21px; font-weight: 650; line-height: 1.35; margin-top: 2px; letter-spacing: 0.2px; }
.value.dd { color: var(--text-1); }
.sub { font-size: 11.5px; color: var(--text-3); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 1100px) { .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; } }
@media (max-width: 600px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; } }
</style>
