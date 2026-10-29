<script setup lang="ts">
// 回撤曲线：策略回撤为浅色面积，基准回撤为细线
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { BacktestPayload } from '@/api/client'
import { axisStyle, baseOption, hexAlpha, useChartTokens } from '@/charts/theme'
import { pct } from '@/utils/format'

const props = withDefaults(defineProps<{ data: BacktestPayload; height?: number; group?: string }>(), { height: 220 })
const tk = useChartTokens()

const option = computed(() => {
  const t = tk.value
  const d = props.data
  const order = (d.config.benchmarks ?? []).filter((c) => d.series.benchmarks[c])
  const nComp = Object.keys(d.series.components).length
  const mdd = d.metrics.max_drawdown_trough
  return {
    ...baseOption(t),
    grid: { left: 8, right: 70, top: 30, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 4, itemGap: 16, textStyle: { color: t.text2, fontSize: 12 } },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      valueFormatter: (v: number) => pct(v, 1),
    },
    xAxis: { type: 'category', data: d.series.dates, boundaryGap: false, ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', max: 0, ...axisStyle(t), axisLabel: { color: t.text3, fontSize: 11, formatter: (v: number) => pct(v, 0) } },
    dataZoom: [{ type: 'inside' }],
    series: [
      {
        name: d.kind === 'portfolio' ? '组合回撤' : '策略回撤',
        type: 'line', data: d.series.drawdown, showSymbol: false, z: 10,
        lineStyle: { width: 1.6, color: t.series[0] }, itemStyle: { color: t.series[0] },
        areaStyle: { color: hexAlpha(t.series[0], 0.14) },
        markPoint: mdd
          ? {
              symbol: 'circle', symbolSize: 9,
              itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
              label: { show: true, position: 'bottom', color: t.text1, fontSize: 11, fontWeight: 600, formatter: () => `最大回撤 ${pct(d.metrics.max_drawdown, 1)}` },
              data: [{ coord: [mdd, d.metrics.max_drawdown] }],
            }
          : undefined,
      },
      ...order.map((code, i) => ({
        name: d.series.benchmarks[code].name + '回撤',
        type: 'line', data: d.series.benchmarks[code].drawdown, showSymbol: false, connectNulls: true,
        lineStyle: { width: 1.2, color: t.series[1 + nComp + i], opacity: 0.85 },
        itemStyle: { color: t.series[1 + nComp + i] },
      })),
    ],
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height + 'px' }" autoresize :group="group" />
</template>
