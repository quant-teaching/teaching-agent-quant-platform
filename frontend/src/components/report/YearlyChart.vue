<script setup lang="ts">
// 年度收益柱状图：按序列身份着色（策略、子策略、基准），数值标在策略柱顶端
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { BacktestPayload } from '@/api/client'
import { axisStyle, baseOption, useChartTokens } from '@/charts/theme'
import { pct } from '@/utils/format'

const props = withDefaults(defineProps<{ data: BacktestPayload; height?: number }>(), { height: 280 })
const tk = useChartTokens()

const option = computed(() => {
  const t = tk.value
  const y = props.data.yearly
  const cols = Object.keys(y.columns).slice(0, 8)
  return {
    ...baseOption(t),
    grid: { left: 8, right: 12, top: 36, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10, itemGap: 16, textStyle: { color: t.text2, fontSize: 12 } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.grid, opacity: 0.6 } }, valueFormatter: (v: number) => pct(v, 1, true) },
    xAxis: { type: 'category', data: y.years.map(String), ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), axisLabel: { color: t.text3, fontSize: 11, formatter: (v: number) => pct(v, 0) } },
    series: cols.map((c, i) => ({
      name: c === '策略' && props.data.kind === 'portfolio' ? '组合' : c,
      type: 'bar',
      color: t.series[i],
      itemStyle: { color: t.series[i] },
      barMaxWidth: 22,
      barGap: '12%',
      data: y.columns[c].map((v) => ({
        value: v,
        itemStyle: { color: t.series[i], borderRadius: (v ?? 0) >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] },
      })),
      label: i === 0
        ? { show: true, position: 'top', color: t.text1, fontSize: 11, fontWeight: 600, formatter: (p: any) => pct(p.value, 1) }
        : undefined,
      labelLayout: { hideOverlap: true },
    })),
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height + 'px' }" autoresize />
</template>
