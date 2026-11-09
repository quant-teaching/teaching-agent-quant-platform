<script setup lang="ts">
// 参数稳健性检验结果：样本内 / 样本外热力图（二维）或柱状图（一维），标出样本内最优（★）与参数高原（◆）。
import { Diamond, Star, TriangleAlert } from 'lucide-vue-next'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { baseOption, useChartTokens } from '@/charts/theme'

const props = defineProps<{ data: any; compact?: boolean }>()
const tk = useChartTokens()
const m = computed(() => props.data.metric as string)
const isPct = computed(() => m.value === 'annual_return' || m.value === 'max_drawdown')
const fmt = (v: number | null | undefined) => (v == null ? '—' : isPct.value ? `${(v * 100).toFixed(1)}%` : v.toFixed(2))
const label = (c: any) => `${props.data.x.title} ${c.x}` + (props.data.y ? ` · ${props.data.y.title} ${c.y}` : '')
const same = (a: any, b: any) => a.x === b.x && a.y === b.y

const range = computed(() => {
  const vals = props.data.cells.filter((c: any) => c.ok).flatMap((c: any) => [c.train[m.value], c.test[m.value]])
  return { min: Math.min(...vals), max: Math.max(...vals) }
})
const rho = computed(() => props.data.spearman as number | null)
const rhoTone = computed(() => (rho.value == null ? '' : rho.value >= 0.5 ? 'good' : rho.value > 0 ? 'mid' : 'bad'))

function heat(seg: 'train' | 'test') {
  const t = tk.value
  const d = props.data
  const xs = d.x.values.map(String)
  const ys = d.y.values.map(String)
  const cells = d.cells.map((c: any, i: number) => {
    const v = c.ok ? c[seg][m.value] : null
    const mark = c.ok && same(c, d.best_train) ? '★' : c.ok && same(c, d.robust) ? '◆' : ''
    return { value: [i % xs.length, Math.floor(i / xs.length), v], mark, c }
  })
  // 指标越高越好（最大回撤为负数，越接近 0 越好），所以统一按"低 → 高"映射为"绿 → 红"
  const { min, max } = range.value
  return {
    ...baseOption(t),
    grid: { left: 8, right: 8, top: 26, bottom: 8, containLabel: true },
    title: { text: seg === 'train' ? `样本内（${d.period[0]} ~ ${d.split} 前）` : `样本外（${d.split} ~ ${d.period[1]}）`,
      left: 'center', top: 0, textStyle: { fontSize: 12, fontWeight: 600, color: t.text2 } },
    tooltip: { ...baseOption(t).tooltip, formatter: (p: any) => {
      const c = p.data.c
      return c.ok ? `${label(c)}<br/>${d.metric_label}：<b>${fmt(p.value[2])}</b>` : `${label(c)}<br/>参数不合法`
    } },
    xAxis: { type: 'category', data: xs, name: d.x.title, nameLocation: 'middle', nameGap: 24, nameTextStyle: { color: t.text3, fontSize: 11 },
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text3, fontSize: 11 } },
    yAxis: { type: 'category', data: ys, name: d.y.title, nameTextStyle: { color: t.text3, fontSize: 11 },
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text3, fontSize: 11 } },
    visualMap: { show: false, type: 'continuous', dimension: 2, min, max: max > min ? max : min + 1e-9, inRange: { color: [t.down, t.neutral, t.up] } },
    series: [{
      type: 'heatmap', data: cells,
      itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 },
      label: { show: true, fontSize: props.compact ? 10 : 11, color: t.text1, formatter: (p: any) => (p.value[2] == null ? '×' : `${p.data.mark}${fmt(p.value[2])}`) },
    }],
  }
}

const bars = computed(() => {
  const t = tk.value
  const d = props.data
  const xs = d.x.values.map(String)
  const pick = (seg: string) => d.cells.map((c: any) => (c.ok ? c[seg][m.value] : null))
  return {
    ...baseOption(t),
    grid: { left: 8, right: 8, top: 30, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: t.text2, fontSize: 11 } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', valueFormatter: (v: number) => fmt(v) },
    xAxis: { type: 'category', data: xs, name: d.x.title, nameLocation: 'middle', nameGap: 24, axisLabel: { color: t.text3 }, nameTextStyle: { color: t.text3, fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { color: t.text3, formatter: (v: number) => fmt(v) }, splitLine: { lineStyle: { color: t.grid } } },
    series: [
      { name: '样本内', type: 'bar', data: pick('train'), itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] } },
      { name: '样本外', type: 'bar', data: pick('test'), itemStyle: { color: t.series[1], borderRadius: [4, 4, 0, 0] } },
    ],
  }
})
const h = computed(() => (props.compact ? 200 : 280) + (props.data.y ? Math.max(0, props.data.y.values.length - 4) * 26 : 0))
</script>

<template>
  <div class="rob" :class="{ compact }">
    <div class="tiles">
      <div class="tile">
        <div class="t-h"><Star :size="13" /> 样本内最优</div>
        <div class="t-l">{{ label(data.best_train) }}</div>
        <div class="t-v">样本内 <b>{{ fmt(data.best_train.train[data.metric]) }}</b> → 样本外 <b>{{ fmt(data.best_train.test[data.metric]) }}</b></div>
        <div class="t-r" :class="{ warn: data.best_train.test_rank > data.count / 2 }">样本外排名 {{ data.best_train.test_rank }} / {{ data.count }}</div>
      </div>
      <div class="tile">
        <div class="t-h"><Diamond :size="13" /> 参数高原</div>
        <div class="t-l">{{ label(data.robust) }}</div>
        <div class="t-v">样本内 <b>{{ fmt(data.robust.train[data.metric]) }}</b> → 样本外 <b>{{ fmt(data.robust.test[data.metric]) }}</b></div>
        <div class="t-r">样本外排名 {{ data.robust.test_rank }} / {{ data.count }}</div>
      </div>
      <div class="tile">
        <div class="t-h">样本内外一致性</div>
        <div class="t-big" :class="rhoTone">{{ rho == null ? '—' : rho.toFixed(2) }}</div>
        <div class="t-r">{{ data.metric_label }}的秩相关系数（1 完全一致，0 无关，负数相反）</div>
      </div>
    </div>

    <div v-if="data.y" class="heats">
      <VChart :option="heat('train')" :style="{ height: h + 'px' }" autoresize />
      <VChart :option="heat('test')" :style="{ height: h + 'px' }" autoresize />
    </div>
    <VChart v-else :option="bars" :style="{ height: h + 'px' }" autoresize />
    <div class="legend-note">★ 样本内最优　◆ 参数高原（与相邻参数平均后最好）　× 参数组合不合法　颜色越红{{ data.metric_label }}越好</div>

    <ul class="concl">
      <li v-for="(c, i) in data.conclusions" :key="i"><TriangleAlert v-if="c.includes('过拟合')" :size="13" class="w" />{{ c }}</li>
    </ul>
  </div>
</template>

<style scoped>
.rob { display: flex; flex-direction: column; gap: 10px; }
.tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.tile { padding: 9px 11px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface-2); min-width: 0; }
.t-h { display: flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 650; color: var(--text-3); }
.t-h svg { color: var(--warn); }
.t-l { font-size: 13px; font-weight: 600; margin: 3px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-v { font-size: 12px; color: var(--text-2); }
.t-r { font-size: 11.5px; color: var(--text-3); margin-top: 2px; }
.t-r.warn { color: var(--up); font-weight: 600; }
.t-big { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
.t-big.good { color: var(--t-green); }
.t-big.mid { color: var(--warn); }
.t-big.bad { color: var(--up); }
.heats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.legend-note { font-size: 11.5px; color: var(--text-3); }
.concl { margin: 0; padding-left: 18px; font-size: 12.5px; line-height: 1.7; color: var(--text-2); }
.concl .w { color: var(--up); margin-right: 4px; vertical-align: -2px; }
.compact .tiles { grid-template-columns: 1fr; }
@media (max-width: 900px) { .heats { grid-template-columns: 1fr; } .tiles { grid-template-columns: 1fr; } }
</style>
