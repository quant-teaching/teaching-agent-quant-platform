<script setup lang="ts">
// 交易点位图：K 线（红涨绿跌）+ 策略指标线 + 买卖点。RSI、MACD 等不在价格量级的指标画在下方副图。
import { NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { ChartData } from '@/api/client'
import { axisStyle, baseOption, hexAlpha, useChartTokens } from '@/charts/theme'

const props = withDefaults(defineProps<{ charts: ChartData[]; height?: number }>(), { height: 460 })
const tk = useChartTokens()
const selected = ref(props.charts[0]?.symbol ?? '')
watch(() => props.charts, (c) => { if (!c.find((x) => x.symbol === selected.value)) selected.value = c[0]?.symbol ?? '' })

const chart = computed(() => props.charts.find((c) => c.symbol === selected.value))
const options = computed(() => props.charts.map((c) => ({ label: `${c.name}（${c.symbol}）· ${c.marks.length} 笔`, value: c.symbol })))

function median(xs: number[]) {
  const s = xs.filter((x) => Number.isFinite(x)).sort((a, b) => a - b)
  return s.length ? s[Math.floor(s.length / 2)] : NaN
}

// 指标线的分类色避开红绿（K 线已用红绿表示涨跌）
const LINE_SLOTS = [0, 1, 6, 3, 4]

const option = computed(() => {
  const t = tk.value
  const c = chart.value
  if (!c) return {}
  const closeMed = median(c.ohlc.map((o) => o[1]))
  const overlay: [string, (number | null)[]][] = []
  const sub: [string, (number | null)[]][] = []
  for (const [name, vals] of Object.entries(c.lines)) {
    const m = median(vals.filter((v): v is number => v !== null))
    if (Number.isFinite(m) && m / closeMed > 0.5 && m / closeMed < 2) overlay.push([name, vals])
    else if (Number.isFinite(m)) sub.push([name, vals])
  }
  const subShown = sub.slice(0, 3)
  const hasSub = subShown.length > 0
  const idx = new Map(c.dates.map((d, i) => [d, i]))
  const buys = c.marks.filter((m) => /买入|开多|加多|平空/.test(m.action))
  const sells = c.marks.filter((m) => !/买入|开多|加多|平空/.test(m.action))
  const markSeries = (list: typeof c.marks, isBuy: boolean) => ({
    name: isBuy ? '买入 / 开多' : '卖出 / 开空',
    type: 'scatter',
    xAxisIndex: 0, yAxisIndex: 0, z: 20,
    symbol: 'triangle', symbolRotate: isBuy ? 0 : 180, symbolSize: 11,
    itemStyle: { color: isBuy ? t.up : t.down, borderColor: t.surface, borderWidth: 1.5 },
    data: list.filter((m) => idx.has(m.date)).map((m) => ({
      value: [m.date, isBuy ? m.price * 0.985 : m.price * 1.015],
      action: m.action, qty: m.qty, price: m.raw_price,
    })),
    tooltip: {
      formatter: (p: any) => `${p.value[0]}<br/><b>${p.data.action}</b> ${Math.abs(p.data.qty)} ${c.symbol.match(/^[A-Z]/) ? '手' : '股'}<br/>成交价 ${p.data.price.toFixed(2)}`,
    },
  })
  const grids = hasSub
    ? [{ left: 8, right: 16, top: 34, height: '58%', containLabel: true }, { left: 8, right: 16, top: '74%', bottom: 30, containLabel: true }]
    : [{ left: 8, right: 16, top: 34, bottom: 40, containLabel: true }]
  const xAxis = grids.map((_, gi) => ({
    type: 'category', data: c.dates, gridIndex: gi, boundaryGap: true, ...axisStyle(t), splitLine: { show: false },
    axisLabel: { ...axisStyle(t).axisLabel, show: gi === grids.length - 1 },
  }))
  // 默认只显示最近约 250 个交易日，买卖点不至于挤在一起；拖动滑块可查看全部
  const startPct = c.dates.length > 250 ? Math.round((1 - 250 / c.dates.length) * 100) : 0
  const yAxis = grids.map((_, gi) => ({ type: 'value', scale: true, gridIndex: gi, ...axisStyle(t), splitNumber: gi ? 2 : 5 }))
  return {
    ...baseOption(t),
    animation: false,
    grid: grids,
    xAxis, yAxis,
    legend: { top: 0, left: 0, itemWidth: 14, itemHeight: 8, itemGap: 14, textStyle: { color: t.text2, fontSize: 12 } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'cross', lineStyle: { color: t.axis }, label: { backgroundColor: t.text3 } } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: [
      { type: 'inside', xAxisIndex: grids.map((_, i) => i), start: startPct, end: 100 },
      { type: 'slider', xAxisIndex: grids.map((_, i) => i), start: startPct, end: 100, height: 18, bottom: 4, borderColor: 'transparent', backgroundColor: t.grid, fillerColor: hexAlpha(t.series[0], 0.12), textStyle: { color: t.text3, fontSize: 10 } },
    ],
    series: [
      {
        name: 'K 线', type: 'candlestick', data: c.ohlc, xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: { color: t.up, color0: t.down, borderColor: t.up, borderColor0: t.down },
        barMaxWidth: 10,
      },
      ...overlay.map(([name, vals], i) => ({
        name, type: 'line', data: vals, showSymbol: false, xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { width: 1.4, color: t.series[LINE_SLOTS[i % LINE_SLOTS.length]] }, itemStyle: { color: t.series[LINE_SLOTS[i % LINE_SLOTS.length]] },
      })),
      ...subShown.map(([name, vals], i) => ({
        name, type: name.includes('柱') ? 'bar' : 'line', data: vals, showSymbol: false, xAxisIndex: 1, yAxisIndex: 1,
        barMaxWidth: 4,
        lineStyle: { width: 1.4, color: t.series[LINE_SLOTS[(overlay.length + i) % LINE_SLOTS.length]] },
        itemStyle: { color: t.series[LINE_SLOTS[(overlay.length + i) % LINE_SLOTS.length]] },
      })),
      markSeries(buys, true),
      markSeries(sells, false),
    ],
  }
})
</script>

<template>
  <div>
    <div class="head">
      <NSelect v-model:value="selected" :options="options" size="small" style="width: 300px" />
      <span class="hint">▲ 红色为买入 / 开多，▼ 绿色为卖出 / 开空；默认显示最近一年，拖动下方滑块查看全部；期货价格为后复权价，与指标同一口径</span>
    </div>
    <VChart v-if="chart" :option="option" :style="{ height: height + 'px' }" autoresize />
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.hint { font-size: 12px; color: var(--text-3); }
</style>
