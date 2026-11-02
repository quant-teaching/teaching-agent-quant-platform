<script setup lang="ts">
// 完整回测报告。compact 模式用于对话页右侧面板
import { AlertTriangle, CalendarRange, Download, Info, Layers, ShieldCheck } from 'lucide-vue-next'
import { NButton, NDataTable, NEmpty, NModal, NTabPane, NTabs, NTag, type DataTableColumns } from 'naive-ui'
import { computed, h, ref, watch } from 'vue'
import { exportUrl, type BacktestPayload, type BenchmarkStats } from '@/api/client'
import { useCatalog } from '@/stores/catalog'
import { money, num, paramValue, pct, signClass } from '@/utils/format'
import CorrelationHeatmap from './CorrelationHeatmap.vue'
import DrawdownChart from './DrawdownChart.vue'
import HoldingsPanel from './HoldingsPanel.vue'
import MetricTiles from './MetricTiles.vue'
import MonthlyHeatmap from './MonthlyHeatmap.vue'
import NavChart from './NavChart.vue'
import TradeChart from './TradeChart.vue'
import TradesTable from './TradesTable.vue'
import YearlyChart from './YearlyChart.vue'

const props = withDefaults(defineProps<{ data: BacktestPayload; compact?: boolean }>(), { compact: false })
const catalog = useCatalog()
const group = computed(() => `bt-${props.data.id}`)
const d = computed(() => props.data)
const diag = computed(() => d.value.diagnostics ?? {})

const paramChips = computed(() => {
  if (d.value.kind === 'portfolio') return []
  const info = catalog.byId(d.value.strategy.id)
  return Object.entries(d.value.params).map(([k, v]) => {
    const spec = info?.params.find((p) => p.key === k)
    return { key: k, title: spec?.title ?? k, value: paramValue(v), changed: spec ? spec.default !== v : false }
  })
})

const universeText = computed(() => {
  const u = d.value.universe
  if (u.length <= 4) return u.map((x) => x.name).join('、')
  return `${u.slice(0, 3).map((x) => x.name).join('、')} 等 ${u.length} 个标的`
})

const benchRows = computed(() => {
  const m = d.value.metrics
  const self = { name: d.value.kind === 'portfolio' ? '组合' : '策略', total_return: m.total_return, annual_return: m.annual_return, max_drawdown: m.max_drawdown, sharpe: m.sharpe, calmar: m.calmar, volatility: m.volatility, self: true } as any
  const order = (d.value.config.benchmarks ?? []).filter((c) => d.value.benchmarks[c])
  return [self, ...order.map((c) => d.value.benchmarks[c])]
})
const benchCols: DataTableColumns<BenchmarkStats & { self?: boolean }> = [
  { title: '', key: 'name', width: 90, render: (r) => h('span', { style: r.self ? 'font-weight:600' : '' }, r.name) },
  { title: '总收益率', key: 'total_return', align: 'right', render: (r) => h('span', { class: 'num ' + signClass(r.total_return) }, pct(r.total_return, 1, true)) },
  { title: '年化收益率', key: 'annual_return', align: 'right', render: (r) => h('span', { class: 'num ' + signClass(r.annual_return) }, pct(r.annual_return, 1, true)) },
  { title: '最大回撤', key: 'max_drawdown', align: 'right', render: (r) => pct(r.max_drawdown, 1) },
  { title: '夏普', key: 'sharpe', align: 'right', render: (r) => num(r.sharpe) },
  { title: '卡玛', key: 'calmar', align: 'right', render: (r) => num(r.calmar) },
  { title: '波动率', key: 'volatility', align: 'right', render: (r) => pct(r.volatility, 1) },
  { title: '超额年化', key: 'excess_annual_return', align: 'right', render: (r) => (r.self ? '—' : h('span', { class: 'num ' + signClass(r.excess_annual_return) }, pct(r.excess_annual_return, 1, true))) },
  { title: 'β', key: 'beta', align: 'right', render: (r) => (r.self ? '—' : num(r.beta)) },
  { title: 'α(年化)', key: 'alpha', align: 'right', render: (r) => (r.self ? '—' : pct(r.alpha, 1, true)) },
  { title: '信息比率', key: 'information_ratio', align: 'right', render: (r) => (r.self ? '—' : num(r.information_ratio)) },
]

const regimeRows = computed(() => {
  const r = diag.value.regimes ?? {}
  return ['上涨月', '震荡月', '下跌月'].filter((k) => r[k]).map((k) => ({ regime: k, ...r[k] }))
})

const compCols: DataTableColumns<any> = [
  { title: '子策略', key: 'label', render: (r) => h('span', { style: 'font-weight:600' }, r.label) },
  { title: '权重', key: 'weight', align: 'right', render: (r) => pct(r.weight, 0) },
  { title: '年化收益率', key: 'ar', align: 'right', render: (r) => h('span', { class: 'num ' + signClass(r.metrics.annual_return) }, pct(r.metrics.annual_return, 1, true)) },
  { title: '最大回撤', key: 'mdd', align: 'right', render: (r) => pct(r.metrics.max_drawdown, 1) },
  { title: '夏普', key: 'sharpe', align: 'right', render: (r) => num(r.metrics.sharpe) },
  { title: '波动率', key: 'vol', align: 'right', render: (r) => pct(r.metrics.volatility, 1) },
  { title: '风险贡献', key: 'rc', align: 'right', render: (_r, i) => pct(diag.value.diversification?.risk_contribution?.[i], 1) },
  { title: '', key: 'open', align: 'right', render: (r) => h('a', { href: `/report/${r.result_id}`, target: '_blank' }, '查看') },
]
const div = computed(() => diag.value.diversification)

// 持仓明细：组合回测没有逐日持仓
const hasHoldings = computed(() => d.value.kind !== 'portfolio')
const lastDate = () => d.value.series.dates[d.value.series.dates.length - 1]
const holdDate = ref(lastDate())
const pickDate = ref('')
const pickOpen = ref(false)
watch(() => d.value.id, () => { holdDate.value = lastDate() })
function onPick(date: string) {
  if (!hasHoldings.value) return
  pickDate.value = date
  pickOpen.value = true
}
</script>

<template>
  <div class="report" :class="{ compact }">
    <!-- 头部 -->
    <div class="head">
      <div class="title-row">
        <h2>{{ d.title }}</h2>
        <NTag v-if="d.kind === 'portfolio'" size="small" type="info" :bordered="false"><template #icon><Layers :size="13" /></template>多策略组合</NTag>
        <NTag v-else size="small" :bordered="false">{{ d.strategy.category === 'futures' ? '期货' : '股票' }} · {{ d.strategy.style }}</NTag>
        <NButton tag="a" :href="exportUrl(d.id)" download size="small" secondary class="export" title="下载 CSV 数据集：每日净值、量化指标、交易记录、成交明细、持仓明细">
          <template #icon><Download :size="14" /></template>导出数据
        </NButton>
      </div>
      <div class="meta">
        <span><CalendarRange :size="14" /> {{ d.config.start }} ~ {{ d.config.end }}</span>
        <span>标的：{{ universeText }}</span>
        <span>初始资金 {{ money(d.metrics.initial_capital) }} → 期末 {{ money(d.metrics.final_equity) }}</span>
        <span v-if="d.metrics.dividends">累计现金分红 {{ money(d.metrics.dividends) }}</span>
      </div>
      <div v-if="paramChips.length" class="chips">
        <span v-for="c in paramChips" :key="c.key" class="chip" :class="{ changed: c.changed }" :title="c.changed ? '已修改（非默认值）' : '默认值'">
          {{ c.title }} <b>{{ c.value }}</b>
        </span>
      </div>
      <div v-else-if="d.kind === 'portfolio'" class="chips">
        <span v-for="(w, k) in d.params.weights" :key="k" class="chip">{{ k }} <b>{{ pct(w as number, 0) }}</b></span>
        <span class="chip">再平衡 <b>{{ { none: '不调仓', M: '每月', Q: '每季度' }[d.params.rebalance as string] }}</b></span>
      </div>
    </div>

    <div v-if="d.warnings.length" class="alert">
      <AlertTriangle :size="15" />
      <div><div v-for="w in d.warnings" :key="w">{{ w }}</div></div>
    </div>

    <MetricTiles :data="d" :columns="compact ? 3 : 5" class="tiles" />

    <NTabs type="line" animated size="medium" class="tabs">
      <NTabPane name="overview" tab="收益与回撤">
        <section class="card card-pad block">
          <h3 class="section-title">净值曲线</h3>
          <p class="section-sub">起点统一为 1.00；拖动下方滑块或滚轮缩放时间范围，点击图例显示 / 隐藏曲线<template v-if="hasHoldings">；点击曲线上的某一天查看当日持仓</template></p>
          <NavChart :data="d" :group="group" :height="compact ? 280 : 360" @pick="onPick" />
        </section>
        <section class="card card-pad block">
          <h3 class="section-title">回撤曲线</h3>
          <p class="section-sub">回撤 = 当前净值 / 历史最高净值 - 1；最大回撤持续 {{ d.metrics.max_drawdown_days }} 个交易日</p>
          <DrawdownChart :data="d" :group="group" :height="compact ? 190 : 220" />
        </section>
        <div class="two" :class="{ one: compact }">
          <section class="card card-pad block">
            <h3 class="section-title">年度收益</h3>
            <p class="section-sub">首尾年份为回测区间内的部分年度</p>
            <YearlyChart :data="d" :height="260" />
          </section>
          <section class="card card-pad block">
            <h3 class="section-title">月度收益（%）</h3>
            <p class="section-sub">红色为上涨月，绿色为下跌月，颜色越深幅度越大</p>
            <MonthlyHeatmap :data="d" />
          </section>
        </div>
        <section class="card card-pad block">
          <h3 class="section-title">与基准对比</h3>
          <p class="section-sub">β 衡量策略随基准涨跌的程度；α 为扣除 β 贡献后的年化超额收益</p>
          <NDataTable :columns="benchCols as any" :data="benchRows" size="small" :bordered="false" :scroll-x="900" />
        </section>
      </NTabPane>

      <NTabPane v-if="d.kind === 'portfolio'" name="portfolio" tab="组合分析">
        <section class="card card-pad block">
          <h3 class="section-title">子策略表现</h3>
          <p class="section-sub">各子策略按全部资金独立回测，组合按权重合成；风险贡献之和为 100%</p>
          <NDataTable :columns="compCols" :data="d.components" size="small" :bordered="false" :scroll-x="760" />
        </section>
        <div v-if="div" class="two" :class="{ one: compact }">
          <section class="card card-pad block">
            <h3 class="section-title">收益相关系数</h3>
            <p class="section-sub">越接近 0 或为负，分散效果越好</p>
            <CorrelationHeatmap :labels="div.labels" :matrix="div.correlation" />
          </section>
          <section class="card card-pad block div-stats">
            <h3 class="section-title">分散化效果</h3>
            <p class="section-sub">分散化比率 = 子策略加权平均波动率 / 组合波动率，大于 1 说明组合降低了波动</p>
            <div class="kv"><span>分散化比率</span><b class="num">{{ num(div.diversification_ratio) }}</b></div>
            <div class="kv"><span>平均相关系数</span><b class="num">{{ num(div.avg_correlation) }}</b></div>
            <div class="kv"><span>子策略加权平均波动率</span><b class="num">{{ pct(div.weighted_avg_vol, 1) }}</b></div>
            <div class="kv"><span>组合波动率</span><b class="num">{{ pct(div.portfolio_vol, 1) }}</b></div>
            <div class="kv"><span>组合最大回撤</span><b class="num">{{ pct(d.metrics.max_drawdown, 1) }}</b></div>
            <div v-for="(v, k) in diag.drawdown_vs_components?.components" :key="k" class="kv sub"><span>{{ k }} 最大回撤</span><b class="num">{{ pct(v as number, 1) }}</b></div>
            <div class="verdict" :class="diag.drawdown_vs_components?.better_than_best_single ? 'good' : ''">
              <ShieldCheck :size="15" />
              {{ diag.drawdown_vs_components?.better_than_best_single ? '组合最大回撤小于每一个子策略，分散化效果明显' : '组合最大回撤没有小于所有子策略，分散化效果有限' }}
            </div>
          </section>
        </div>
      </NTabPane>

      <NTabPane v-if="d.charts.length" name="marks" tab="交易点位">
        <section class="card card-pad block">
          <h3 class="section-title">K 线与买卖点</h3>
          <p class="section-sub">展示交易最活跃的 {{ d.charts.length }} 个标的；叠加策略使用的指标线，帮助理解每一次信号</p>
          <TradeChart :charts="d.charts" :height="compact ? 400 : 480" />
        </section>
      </NTabPane>

      <NTabPane name="trades" tab="交易明细">
        <section class="card card-pad block">
          <TradesTable :trades="d.trades" :fills="d.fills" :fills-truncated="d.fills_truncated" :fill-total="d.fill_total" />
        </section>
        <section v-if="hasHoldings" class="card card-pad block">
          <h3 class="section-title">持仓明细</h3>
          <HoldingsPanel v-model:date="holdDate" :result-id="d.id" :dates="d.series.dates" :futures="d.strategy.category === 'futures'" />
        </section>
      </NTabPane>

      <NTabPane name="diagnose" tab="诊断分析">
        <div class="two" :class="{ one: compact }">
          <section class="card card-pad block">
            <h3 class="section-title">不同行情下的表现</h3>
            <p class="section-sub">按{{ diag.regime_benchmark ?? '基准' }}当月涨跌划分：涨超 3% 为上涨月，跌超 3% 为下跌月，其余为震荡月</p>
            <table v-if="regimeRows.length" class="mini">
              <thead><tr><th>行情</th><th>月数</th><th>策略平均月收益</th><th>基准平均月收益</th><th>策略盈利月占比</th></tr></thead>
              <tbody>
                <tr v-for="r in regimeRows" :key="r.regime">
                  <td>{{ r.regime }}</td><td class="num">{{ r.months }}</td>
                  <td class="num" :class="signClass(r.strategy_avg_monthly)">{{ pct(r.strategy_avg_monthly, 2, true) }}</td>
                  <td class="num" :class="signClass(r.benchmark_avg_monthly)">{{ pct(r.benchmark_avg_monthly, 2, true) }}</td>
                  <td class="num">{{ pct(r.strategy_win_months, 0) }}</td>
                </tr>
              </tbody>
            </table>
            <NEmpty v-else description="没有基准数据" size="small" />
          </section>
          <section class="card card-pad block">
            <h3 class="section-title">主要回撤区间</h3>
            <p class="section-sub">从高点到谷底，以及净值重新回到高点的日期</p>
            <table class="mini">
              <thead><tr><th>回撤</th><th>高点</th><th>谷底</th><th>恢复</th><th>持续</th></tr></thead>
              <tbody>
                <tr v-for="x in diag.top_drawdowns ?? []" :key="x.peak">
                  <td class="num"><b>{{ pct(x.drawdown, 1) }}</b></td><td class="num">{{ x.peak }}</td><td class="num">{{ x.trough }}</td>
                  <td class="num">{{ x.recovery ?? '未恢复' }}</td><td class="num">{{ x.days }} 天</td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>
        <section class="card card-pad block">
          <h3 class="section-title">交易行为</h3>
          <div class="facts">
            <div class="fact"><span>平均持仓天数</span><b class="num">{{ num(d.metrics.avg_holding_days, 1) }}</b></div>
            <div class="fact"><span>平均仓位</span><b class="num">{{ pct(d.metrics.avg_gross_exposure, 0) }}</b></div>
            <div class="fact"><span>持仓时间占比</span><b class="num">{{ pct(diag.time_in_market, 0) }}</b></div>
            <div class="fact"><span>最长连续亏损</span><b class="num">{{ diag.max_consecutive_losses ?? '—' }} 笔</b></div>
            <div class="fact"><span>≤3 天短线占比</span><b class="num">{{ pct(diag.short_trade_ratio, 0) }}</b></div>
            <div class="fact"><span>成本年化拖累</span><b class="num">{{ pct(diag.cost_drag_annual, 2) }}</b></div>
            <div class="fact"><span>索提诺比率</span><b class="num">{{ num(d.metrics.sortino) }}</b></div>
            <div v-if="diag.blocked_orders" class="fact"><span>涨跌停/停牌未成交</span><b class="num">{{ diag.blocked_orders }} 次</b></div>
            <div v-if="diag.long_pnl !== undefined" class="fact"><span>多头合计盈亏</span><b class="num" :class="signClass(diag.long_pnl)">{{ money(diag.long_pnl) }}</b></div>
            <div v-if="diag.short_pnl !== undefined" class="fact"><span>空头合计盈亏</span><b class="num" :class="signClass(diag.short_pnl)">{{ money(diag.short_pnl) }}</b></div>
          </div>
          <div v-if="diag.top_contributors?.length" class="contrib">
            <span class="muted">盈利贡献最大：</span>{{ diag.top_contributors.map((c: any) => c.name).join('、') }}
            <template v-if="diag.bottom_contributors?.length"><span class="muted" style="margin-left:16px">亏损最多：</span>{{ diag.bottom_contributors.map((c: any) => c.name).join('、') }}</template>
          </div>
        </section>
      </NTabPane>
    </NTabs>

    <div v-for="n in d.notes" :key="n" class="note"><Info :size="14" /> {{ n }}</div>
    <div class="disclaimer">⚠️ 本结果为教学回测模拟，历史回测不代表未来表现，不构成任何投资建议。</div>

    <NModal v-model:show="pickOpen" preset="card" title="当日持仓" :bordered="false" style="width: 760px; max-width: calc(100vw - 32px)">
      <HoldingsPanel v-model:date="pickDate" :result-id="d.id" :dates="d.series.dates" :futures="d.strategy.category === 'futures'" />
    </NModal>
  </div>
</template>

<style scoped>
.report { display: flex; flex-direction: column; gap: 14px; }
.report > * { animation: rise 0.5s var(--ease-out) both; }
.report > :nth-child(2) { animation-delay: 0.06s; }
.report > :nth-child(3) { animation-delay: 0.12s; }
.report > :nth-child(n + 4) { animation-delay: 0.18s; }
.block { animation: rise 0.45s var(--ease-out) both; }
.block:nth-child(2) { animation-delay: 0.06s; }
.block:nth-child(n + 3) { animation-delay: 0.12s; }
.head h2 { font-size: 20px; font-weight: 650; margin: 0; }
.compact .head h2 { font-size: 17px; }
.title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.export { margin-left: auto; }
.meta { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 6px; font-size: 12.5px; color: var(--text-3); }
.meta span { display: inline-flex; align-items: center; gap: 5px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.chip { font-size: 12px; padding: 2px 9px; border-radius: 999px; background: var(--surface-3); color: var(--text-2); }
.chip b { font-weight: 600; color: var(--text-1); margin-left: 2px; }
.chip.changed { background: var(--primary-soft); color: var(--primary-ink); }
.chip.changed b { color: var(--primary-ink); }
.alert { display: flex; gap: 8px; align-items: flex-start; padding: 10px 14px; border-radius: 10px; background: var(--warn-soft); color: var(--text-2); font-size: 12.5px; }
.alert svg { color: var(--warn); flex-shrink: 0; margin-top: 3px; }
.tabs :deep(.n-tabs-pane-wrapper) { overflow: visible; }
.block { margin-bottom: 14px; }
.two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.two > .block { margin-bottom: 14px; }
.two.one { grid-template-columns: minmax(0, 1fr); gap: 0; }
@media (max-width: 1100px) { .two { grid-template-columns: minmax(0, 1fr); gap: 0; } }
.mini { width: 100%; border-collapse: collapse; font-size: 13px; }
.mini th { text-align: left; font-weight: 500; color: var(--text-3); font-size: 12px; padding: 6px 8px; border-bottom: 1px solid var(--border); }
.mini td { padding: 8px; border-bottom: 1px solid var(--border); }
.mini tr:last-child td { border-bottom: none; }
.facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin-top: 8px; }
.fact { display: flex; flex-direction: column; padding: 10px 12px; background: var(--surface-2); border-radius: 10px; }
.fact span { font-size: 12px; color: var(--text-3); }
.fact b { font-size: 16px; font-weight: 600; }
.contrib { margin-top: 12px; font-size: 13px; color: var(--text-2); }
.div-stats .kv { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.div-stats .kv.sub { color: var(--text-3); font-size: 12.5px; }
.div-stats .kv span { color: var(--text-2); }
.verdict { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: 13px; padding: 8px 12px; border-radius: 8px; background: var(--surface-3); color: var(--text-2); }
.verdict.good { background: var(--primary-soft); color: var(--primary-ink); }
.note { display: flex; gap: 6px; align-items: flex-start; font-size: 12.5px; color: var(--text-3); }
.note svg { margin-top: 3px; flex-shrink: 0; }
.disclaimer { font-size: 12.5px; color: var(--text-3); padding: 10px 14px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; }
</style>
