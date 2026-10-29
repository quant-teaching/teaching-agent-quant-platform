<script setup lang="ts">
// 子策略收益相关系数矩阵：蓝（负相关）— 灰（不相关）— 红（正相关），格内标注数值
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { baseOption, useChartTokens } from '@/charts/theme'

const props = defineProps<{ labels: string[]; matrix: number[][] }>()
const tk = useChartTokens()

const option = computed(() => {
  const t = tk.value
  const n = props.labels.length
  const data: any[] = []
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const v = props.matrix[i][j]
    data.push([j, i, v])
  }
  return {
    ...baseOption(t),
    grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
    tooltip: { ...baseOption(t).tooltip, formatter: (p: any) => `${props.labels[p.value[1]]} × ${props.labels[p.value[0]]}<br/>相关系数 <b>${p.value[2].toFixed(2)}</b>` },
    xAxis: { type: 'category', data: props.labels, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text2, fontSize: 11, interval: 0 } },
    yAxis: { type: 'category', data: props.labels, inverse: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text2, fontSize: 11 } },
    // 蓝（负相关）— 灰（不相关）— 红（正相关）
    visualMap: { show: false, type: 'continuous', dimension: 2, min: -1, max: 1, inRange: { color: [t.series[0], t.neutral, t.series[7]] } },
    series: [{
      type: 'heatmap', data,
      itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 6 },
      label: { show: true, color: t.text1, fontSize: 12, fontWeight: 600, formatter: (p: any) => p.value[2].toFixed(2) },
    }],
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: Math.max(180, labels.length * 56 + 40) + 'px' }" autoresize />
</template>
