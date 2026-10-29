<script setup lang="ts">
// 迷你净值线：对话卡片和历史列表中使用，只画一条线和基准线 1.0
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { hexAlpha, useChartTokens } from '@/charts/theme'

const props = withDefaults(defineProps<{ values: (number | null)[]; bench?: (number | null)[]; height?: number }>(), { height: 56 })
const tk = useChartTokens()
const option = computed(() => {
  const t = tk.value
  return {
    animation: false,
    grid: { left: 0, right: 0, top: 4, bottom: 4 },
    xAxis: { type: 'category', show: false, boundaryGap: false, data: props.values.map((_, i) => i) },
    yAxis: { type: 'value', show: false, scale: true },
    series: [
      ...(props.bench ? [{ type: 'line', data: props.bench, showSymbol: false, lineStyle: { width: 1, color: t.text3, opacity: 0.6 }, silent: true }] : []),
      { type: 'line', data: props.values, showSymbol: false, lineStyle: { width: 1.8, color: t.series[0] }, areaStyle: { color: hexAlpha(t.series[0], 0.1), origin: 'start' }, silent: true },
    ],
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height + 'px' }" autoresize />
</template>
