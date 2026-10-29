<script setup lang="ts">
// 月度收益热力图：红涨绿跌、中性灰居中，每格标注数值（颜色之外的第二编码）
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { BacktestPayload } from '@/api/client'
import { baseOption, useChartTokens } from '@/charts/theme'
import { pct } from '@/utils/format'

const props = withDefaults(defineProps<{ data: BacktestPayload }>(), {})
const tk = useChartTokens()

const grid = computed(() => {
  const years = [...new Set(props.data.monthly.map((m) => m.month.slice(0, 4)))]
  const cells = props.data.monthly
    .filter((m) => m.ret !== null)
    .map((m) => [Number(m.month.slice(5, 7)) - 1, years.indexOf(m.month.slice(0, 4)), m.ret as number])
  const max = Math.max(0.05, ...cells.map((c) => Math.abs(c[2])))
  return { years, cells, max }
})

const option = computed(() => {
  const t = tk.value
  const { years, cells, max } = grid.value
  return {
    ...baseOption(t),
    grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      ...baseOption(t).tooltip,
      formatter: (p: any) => `${years[p.value[1]]} 年 ${p.value[0] + 1} 月<br/><b>${pct(p.value[2], 2, true)}</b>`,
    },
    xAxis: {
      type: 'category', data: Array.from({ length: 12 }, (_, i) => `${i + 1}月`),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text3, fontSize: 11 }, splitArea: { show: false },
    },
    yAxis: {
      type: 'category', data: years, inverse: true,
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text3, fontSize: 11 },
    },
    // 连续视觉映射：绿（跌）— 中性灰 — 红（涨），以 0 为中点对称
    visualMap: { show: false, type: 'continuous', dimension: 2, min: -max, max, inRange: { color: [t.down, t.neutral, t.up] } },
    series: [{
      type: 'heatmap',
      data: cells,
      itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 },
      label: { show: true, fontSize: 10.5, color: t.text1, formatter: (p: any) => (p.value[2] * 100).toFixed(1) },
      emphasis: { itemStyle: { borderColor: t.text2, borderWidth: 1 } },
    }],
  }
})
const height = computed(() => Math.max(140, grid.value.years.length * 34 + 40))
</script>

<template>
  <VChart :option="option" :style="{ height: height + 'px' }" autoresize />
</template>
