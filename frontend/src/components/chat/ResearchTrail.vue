<script setup lang="ts">
// 自主研究的探索轨迹：按时间顺序展示智能体每一次回测尝试的参数与结果，不同颜色表示第几轮迭代。
import { Route } from 'lucide-vue-next'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { baseOption, useChartTokens } from '@/charts/theme'
import type { Block } from './types'

const props = defineProps<{ blocks: Block[] }>()
const emit = defineEmits<{ open: [id: string] }>()
const tk = useChartTokens()

const attempts = computed(() => {
  let round = 1
  const out: { i: number; round: number; title: string; params: string; m: any; id: string }[] = []
  for (const b of props.blocks) {
    if (b.kind === 'phase' && b.name === 'iteration' && b.iteration) round = b.iteration
    if (b.kind === 'tool' && b.status === 'ok' && b.card?.kind === 'backtest') {
      const ch = b.card.changed ?? {}
      const params = Object.keys(ch).length ? Object.entries(ch).map(([k, v]) => `${k}=${v}`).join(', ') : '默认参数'
      out.push({ i: out.length + 1, round, title: b.card.title, params, m: b.card.metrics, id: b.card.result_id })
    }
  }
  return out
})

const option = computed(() => {
  const t = tk.value
  const a = attempts.value
  const pct = (v: number | null) => (v == null ? null : +(v * 100).toFixed(2))
  return {
    ...baseOption(t),
    grid: { left: 8, right: 40, top: 34, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: t.text2, fontSize: 11 } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', formatter: (ps: any[]) => {
      const x = a[ps[0].dataIndex]
      return `尝试 #${x.i}（第 ${x.round} 轮）<br/>${x.title}<br/><span style="opacity:.7">${x.params}</span><br/>` +
        ps.map((p) => `${p.marker}${p.seriesName}：<b>${p.seriesName === '夏普比率' ? p.value : p.value + '%'}</b>`).join('<br/>')
    } },
    xAxis: { type: 'category', data: a.map((x) => `#${x.i}\n第${x.round}轮`), axisLabel: { color: t.text3, fontSize: 10.5 } },
    yAxis: [
      { type: 'value', name: '%', axisLabel: { color: t.text3 }, splitLine: { lineStyle: { color: t.grid } }, nameTextStyle: { color: t.text3 } },
      { type: 'value', name: '夏普', axisLabel: { color: t.text3 }, splitLine: { show: false }, nameTextStyle: { color: t.text3 } },
    ],
    series: [
      { name: '年化收益率', type: 'bar', data: a.map((x) => pct(x.m.annual_return)), itemStyle: { color: t.series[0], borderRadius: [3, 3, 0, 0] } },
      { name: '最大回撤', type: 'bar', data: a.map((x) => pct(x.m.max_drawdown)), itemStyle: { color: t.series[1], borderRadius: [0, 0, 3, 3] } },
      { name: '夏普比率', type: 'line', yAxisIndex: 1, data: a.map((x) => (x.m.sharpe == null ? null : +x.m.sharpe.toFixed(2))),
        itemStyle: { color: t.series[2] }, symbolSize: 7, label: { show: true, color: t.text2, fontSize: 10, position: 'top' } },
    ],
  }
})
</script>

<template>
  <div v-if="attempts.length >= 2" class="trail">
    <div class="title"><Route :size="15" /> 研究轨迹：智能体的 {{ attempts.length }} 次尝试</div>
    <VChart :option="option" style="height: 230px" autoresize />
    <ol>
      <li v-for="x in attempts" :key="x.i">
        <a href="#" @click.prevent="emit('open', x.id)">#{{ x.i }}</a>
        <span class="r">第 {{ x.round }} 轮</span>{{ x.params }}
      </li>
    </ol>
  </div>
</template>

<style scoped>
.trail { margin: 10px 0; padding: 12px 14px; border-radius: 12px; border: 1px solid color-mix(in srgb, var(--t-teal) 35%, var(--border)); background: var(--surface); animation: pop 0.35s var(--ease-out) both; }
.title { display: flex; align-items: center; gap: 6px; font-weight: 650; font-size: 13.5px; margin-bottom: 4px; }
.title svg { color: var(--t-teal); }
ol { margin: 6px 0 0; padding-left: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 2px 12px; font-size: 12px; color: var(--text-2); }
ol a { font-weight: 700; margin-right: 6px; }
.r { color: var(--text-3); margin-right: 6px; }
</style>
