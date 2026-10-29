<script setup lang="ts">
// 净值曲线：策略（或组合）+ 子策略 + 基准指数，起点统一为 1
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { BacktestPayload } from '@/api/client'
import { axisStyle, baseOption, hexAlpha, useChartTokens } from '@/charts/theme'
import { pct } from '@/utils/format'

const props = withDefaults(defineProps<{ data: BacktestPayload; height?: number; group?: string; compact?: boolean }>(), {
  height: 340,
  compact: false,
})
const tk = useChartTokens()

const series = computed(() => {
  const d = props.data
  const out: { name: string; values: (number | null)[]; main?: boolean }[] = [
    { name: d.kind === 'portfolio' ? '组合' : '策略', values: d.series.nav, main: true },
  ]
  for (const [label, v] of Object.entries(d.series.components)) out.push({ name: label, values: v })
  const order = (d.config.benchmarks ?? ['000300', '000905', '399006']).filter((c) => d.series.benchmarks[c])
  for (const code of order) out.push({ name: d.series.benchmarks[code].name, values: d.series.benchmarks[code].nav })
  return out.slice(0, 8) // 分类色只有 8 个，超出的不画（图例与表格中仍可查看）
})

const option = computed(() => {
  const t = tk.value
  const dates = props.data.series.dates
  return {
    ...baseOption(t),
    color: t.series,
    grid: { left: 8, right: props.compact ? 16 : 70, top: 36, bottom: props.compact ? 24 : 56, containLabel: true },
    legend: {
      top: 0, left: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 4, itemGap: 16,
      textStyle: { color: t.text2, fontSize: 12 },
    },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.axis } },
      formatter: (ps: any[]) => {
        const rows = ps
          .filter((p) => p.value !== null && p.value !== undefined)
          .map((p) => `<div style="display:flex;justify-content:space-between;gap:18px;align-items:center">
              <span><span style="display:inline-block;width:10px;height:3px;border-radius:2px;background:${p.color};margin-right:6px;vertical-align:middle"></span>${p.seriesName}</span>
              <span style="font-variant-numeric:tabular-nums"><b>${Number(p.value).toFixed(3)}</b>
              <span style="color:${t.text3};margin-left:6px">${pct(p.value - 1, 1, true)}</span></span></div>`)
          .join('')
        return `<div style="font-weight:600;margin-bottom:4px">${ps[0]?.axisValue ?? ''}</div>${rows}`
      },
    },
    xAxis: { type: 'category', data: dates, boundaryGap: false, ...axisStyle(t), splitLine: { show: false } },
    yAxis: {
      type: 'value', scale: true, ...axisStyle(t),
      axisLabel: { color: t.text3, fontSize: 11, formatter: (v: number) => v.toFixed(2) },
    },
    dataZoom: props.compact
      ? [{ type: 'inside' }]
      : [
          { type: 'inside' },
          {
            type: 'slider', height: 20, bottom: 6, borderColor: 'transparent', backgroundColor: t.grid,
            fillerColor: hexAlpha(t.series[0], 0.12), handleStyle: { color: t.surface, borderColor: t.axis },
            dataBackground: { lineStyle: { color: t.axis }, areaStyle: { color: t.grid } },
            textStyle: { color: t.text3, fontSize: 10 },
          },
        ],
    series: series.value.map((s, i) => ({
      name: s.name,
      type: 'line',
      data: s.values,
      showSymbol: false,
      symbolSize: 8,
      connectNulls: true,
      z: s.main ? 10 : 2,
      lineStyle: { width: s.main ? 2.2 : 1.6, opacity: s.main ? 1 : 0.9, cap: 'round', join: 'round' },
      emphasis: { focus: 'series', lineStyle: { width: s.main ? 2.6 : 2.2 } },
      areaStyle: s.main ? { color: hexAlpha(t.series[i], 0.08), origin: 'start' } : undefined,
      endLabel: s.main && !props.compact
        ? { show: true, color: t.text1, fontSize: 12, fontWeight: 600, formatter: (p: any) => pct(p.value - 1, 1, true) }
        : undefined,
      markLine: s.main
        ? { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: t.axis, width: 1, type: 'solid' }, data: [{ yAxis: 1 }] }
        : undefined,
    })),
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height + 'px' }" autoresize :group="group" />
</template>
