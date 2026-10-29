<script setup lang="ts">
// 工具结果卡片：策略、参数对比、回测摘要、组合、参数实验、知识来源
import { ArrowRight, BookOpen, ChartLine, Layers } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { getBacktest, type BacktestPayload } from '@/api/client'
import Sparkline from '@/components/report/Sparkline.vue'
import { num, paramValue, pct, signClass } from '@/utils/format'

const props = defineProps<{ card: any }>()
const emit = defineEmits<{ open: [id: string] }>()
const payload = ref<BacktestPayload | null>(null)

onMounted(async () => {
  if ((props.card.kind === 'backtest' || props.card.kind === 'portfolio') && props.card.result_id) {
    try {
      payload.value = await getBacktest(props.card.result_id)
    } catch { /* 结果可能已被删除 */ }
  }
})

const m = computed(() => props.card.metrics ?? {})
const hs = computed(() => payload.value?.series.benchmarks['000300']?.nav)
</script>

<template>
  <!-- 策略 -->
  <div v-if="card.kind === 'strategy'" class="tcard">
    <div class="tc-head">
      <BookOpen :size="15" class="ic" />
      <b>{{ card.name }}</b>
      <span class="tag-soft">{{ card.category === 'futures' ? '期货' : '股票' }} · {{ card.style }}</span>
      <RouterLink :to="`/library/${card.id}`" class="link" target="_blank">算法库 <ArrowRight :size="12" /></RouterLink>
    </div>
    <div class="summary">{{ card.summary }}</div>
    <div class="params">
      <span v-for="p in card.params" :key="p.key" class="pchip" :class="{ changed: p.current !== p.default }" :title="p.description">
        {{ p.title }} <b>{{ paramValue(p.current) }}</b>
      </span>
    </div>
  </div>

  <!-- 参数修改 -->
  <div v-else-if="card.kind === 'param_diff'" class="tcard">
    <div class="tc-head"><b>{{ card.strategy }}</b><span class="muted">参数已更新</span></div>
    <div v-if="card.changes.length" class="diff">
      <div v-for="c in card.changes" :key="c.key" class="diff-row">
        <span class="dl">{{ c.title }}</span>
        <span class="old num">{{ paramValue(c.old) }}</span>
        <ArrowRight :size="13" class="muted" />
        <span class="new num">{{ paramValue(c.new) }}</span>
      </div>
    </div>
    <div v-else class="muted small">参数值与当前一致，没有变化</div>
  </div>

  <!-- 单策略 / 组合回测 -->
  <div v-else-if="card.kind === 'backtest' || card.kind === 'portfolio'" class="tcard bt" role="button" tabindex="0" @click="emit('open', card.result_id)" @keydown.enter="emit('open', card.result_id)">
    <div class="tc-head">
      <component :is="card.kind === 'portfolio' ? Layers : ChartLine" :size="15" class="ic" />
      <b>{{ card.title }}</b>
      <span class="muted small">{{ card.period }}</span>
      <span class="link">查看完整报告 <ArrowRight :size="12" /></span>
    </div>
    <div class="bt-body">
      <div class="kpis">
        <div><span>总收益率</span><b class="num" :class="signClass(m.total_return)">{{ pct(m.total_return, 1, true) }}</b></div>
        <div><span>年化收益率</span><b class="num" :class="signClass(m.annual_return)">{{ pct(m.annual_return, 1, true) }}</b></div>
        <div><span>最大回撤</span><b class="num">{{ pct(m.max_drawdown, 1) }}</b></div>
        <div><span>夏普比率</span><b class="num">{{ num(m.sharpe) }}</b></div>
        <div><span>胜率</span><b class="num">{{ pct(m.win_rate, 1) }}</b></div>
        <div><span>沪深300 年化</span><b class="num" :class="signClass(m.hs300_annual_return)">{{ pct(m.hs300_annual_return, 1, true) }}</b></div>
      </div>
      <div class="spark">
        <Sparkline v-if="payload" :values="payload.series.nav" :bench="hs" :height="64" />
        <div class="spark-legend"><i class="k1" />{{ card.kind === 'portfolio' ? '组合' : '策略' }}<i class="k2" />沪深300</div>
      </div>
    </div>
    <div v-if="card.components" class="params">
      <span v-for="c in card.components" :key="c.result_id" class="pchip">{{ c.name }} <b>{{ pct(c.weight, 0) }}</b></span>
    </div>
  </div>

  <!-- 参数对比实验 -->
  <div v-else-if="card.kind === 'param_compare'" class="tcard">
    <div class="tc-head"><b>{{ card.strategy }}</b><span class="muted small">参数对比：{{ card.param }}</span></div>
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>{{ card.param }}</th><th>年化收益率</th><th>最大回撤</th><th>夏普</th><th>胜率</th><th>交易次数</th><th>成本占比</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in card.rows" :key="r.result_id">
            <td><b>{{ paramValue(r[card.param]) }}</b></td>
            <td class="num">{{ r['年化收益率'] }}</td><td class="num">{{ r['最大回撤'] }}</td><td class="num">{{ r['夏普比率'] }}</td>
            <td class="num">{{ r['胜率'] }}</td><td class="num">{{ r['交易次数'] }}</td><td class="num">{{ r['成本占比'] }}</td>
            <td><a href="#" @click.prevent="emit('open', r.result_id)">报告</a></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 知识库 -->
  <div v-else-if="card.kind === 'knowledge' && card.sources?.length" class="sources">
    <span class="muted small">参考：</span>
    <span v-for="s in card.sources" :key="s" class="src">{{ s }}</span>
  </div>

  <div v-else-if="card.kind === 'derived_saved'" class="tcard">
    <div class="tc-head"><b>已保存衍生策略「{{ card.name }}」</b><RouterLink :to="`/library/${card.id}`" class="link" target="_blank">查看 <ArrowRight :size="12" /></RouterLink></div>
    <div class="muted small">基于 {{ card.base }}，可在算法库中直接调取</div>
  </div>

  <div v-else-if="card.kind === 'strategy_list'" class="params">
    <RouterLink v-for="s in card.items.slice(0, 30)" :key="s.id" :to="`/library/${s.id}`" target="_blank" class="pchip">{{ s.name }}</RouterLink>
  </div>
</template>

<style scoped>
.tcard { border: 1px solid var(--border); background: var(--surface); border-radius: 12px; padding: 12px 14px; margin: 6px 0 4px; }
.tcard.bt { cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }
.tcard.bt:hover { border-color: var(--primary); box-shadow: var(--shadow-md); }
.tc-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13.5px; }
.ic { color: var(--primary); }
.link { margin-left: auto; font-size: 12.5px; color: var(--primary); display: inline-flex; align-items: center; gap: 2px; }
.small { font-size: 12px; }
.summary { font-size: 13px; color: var(--text-2); margin: 6px 0 8px; }
.params { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.pchip { font-size: 12px; padding: 2px 9px; border-radius: 999px; background: var(--surface-3); color: var(--text-2); }
.pchip b { color: var(--text-1); font-weight: 600; margin-left: 2px; }
.pchip.changed { background: var(--primary-soft); color: var(--primary-ink); }
.diff { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.diff-row { display: grid; grid-template-columns: minmax(110px, auto) auto 16px auto; gap: 8px; align-items: center; font-size: 13px; justify-content: start; }
.dl { color: var(--text-2); }
.old { color: var(--text-3); text-decoration: line-through; }
.new { color: var(--primary-ink); font-weight: 650; }
.bt-body { display: grid; grid-template-columns: 1fr 200px; gap: 14px; margin-top: 10px; align-items: center; }
.kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: 8px 14px; }
.kpis div { display: flex; flex-direction: column; }
.kpis span { font-size: 11.5px; color: var(--text-3); white-space: nowrap; }
.kpis b { font-size: 16px; font-weight: 650; }
.spark-legend { display: flex; gap: 6px; align-items: center; font-size: 11px; color: var(--text-3); justify-content: flex-end; }
.spark-legend i { display: inline-block; width: 12px; height: 3px; border-radius: 2px; margin-left: 6px; }
.k1 { background: var(--primary); }
.k2 { background: var(--text-3); opacity: 0.6; }
.tbl-wrap { overflow-x: auto; margin-top: 8px; }
.tbl { border-collapse: collapse; font-size: 12.5px; width: 100%; }
.tbl th { color: var(--text-3); font-weight: 500; text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.tbl td { padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.tbl tr:last-child td { border-bottom: none; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 2px 0; }
.src { font-size: 11.5px; padding: 1px 8px; border-radius: 6px; border: 1px solid var(--border); color: var(--text-2); }
@media (max-width: 760px) { .bt-body { grid-template-columns: 1fr; } }
</style>
