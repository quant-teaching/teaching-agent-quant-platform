<script setup lang="ts">
// 数据核验：让人自己验证回测结果是真实的，而不是只能相信"核验通过"。
// 1. 指标复算：浏览器用每日净值独立重算指标，和引擎给出的结果对照（与后端代码无关）；
// 2. 账本对账：后端不经过回测引擎，用原始行情和成交记录重算期末权益；
// 3. 逐笔成交核对：每笔成交的当日开盘价、成交价与手续费计算式，可以拿计算器和行情软件对照。
import { CircleCheck, CircleX, Calculator, ScrollText, Scale } from 'lucide-vue-next'
import { NDataTable, NSpin, type DataTableColumns } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { api, type BacktestPayload } from '@/api/client'
import { num, pct } from '@/utils/format'

const props = defineProps<{ data: BacktestPayload }>()
const yuan = (v: number) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const audit = ref<any>(null)
const loading = ref(true)
const failed = ref('')

onMounted(async () => {
  try { audit.value = await api.get(`/api/backtests/${props.data.id}/audit`) } catch (e: any) { failed.value = e.message } finally { loading.value = false }
})

// ---- 1. 浏览器独立复算
const recomputed = computed(() => {
  const nav = (props.data.series.nav as (number | null)[]).filter((x): x is number => x != null)
  const n = nav.length - 1
  const rets = nav.slice(1).map((v, i) => v / nav[i] - 1)
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length
  const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1))
  let peak = nav[0], mdd = 0
  for (const v of nav) { peak = Math.max(peak, v); mdd = Math.min(mdd, v / peak - 1) }
  const rf = Number((props.data.config as any).risk_free_rate ?? 0) / 252
  const ann = (nav[n] / nav[0]) ** (252 / n) - 1
  return {
    total_return: nav[n] / nav[0] - 1,
    annual_return: ann,
    max_drawdown: mdd,
    volatility: sd * Math.sqrt(252),
    sharpe: sd > 0 ? ((mean - rf) / sd) * Math.sqrt(252) : 0,
    calmar: mdd < 0 ? ann / Math.abs(mdd) : 0,
  }
})
const ROWS: [string, string, boolean, string][] = [
  ['total_return', '总收益率', true, '期末净值 ÷ 期初净值 − 1'],
  ['annual_return', '年化收益率', true, '(期末 ÷ 期初)^(252 ÷ 交易日数) − 1'],
  ['max_drawdown', '最大回撤', true, '净值相对历史最高点的最大跌幅'],
  ['volatility', '年化波动率', true, '日收益率标准差 × √252'],
  ['sharpe', '夏普比率', false, '日均收益 ÷ 日收益标准差 × √252'],
  ['calmar', '卡玛比率', false, '年化收益率 ÷ |最大回撤|'],
]
const metricRows = computed(() => ROWS.map(([k, label, isPct, formula]) => {
  const eng = (props.data.metrics as any)[k] as number
  const web = (recomputed.value as any)[k] as number
  const show = (v: number) => (isPct ? pct(v, 2) : num(v, 3))
  return { label, formula, eng: show(eng), web: show(web), ok: show(eng) === show(web) || Math.abs(eng - web) < (isPct ? 5e-4 : 5e-3) }
}))
const allMetricsOk = computed(() => metricRows.value.every((r) => r.ok))

// ---- 3. 逐笔成交
const isFut = computed(() => props.data.strategy?.category === 'futures')
const ok = (v: boolean) => h(v ? CircleCheck : CircleX, { size: 15, class: v ? 'ok-ic' : 'bad-ic' })
const fillCols = computed<DataTableColumns<any>>(() => {
  const base: DataTableColumns<any> = [
    { title: '日期', key: 'date', width: 100 },
    { title: '标的', key: 'name', width: 110, render: (r) => `${r.name}（${r.contract || r.symbol}）` },
    { title: '动作', key: 'action', width: 60 },
    { title: '数量', key: 'qty', width: 80, align: 'right', render: (r) => Math.abs(r.qty).toLocaleString() },
    { title: '当日开盘价', key: 'open', width: 96, align: 'right', render: (r) => (r.open == null ? '—' : r.open.toFixed(2)) },
  ]
  if (isFut.value) {
    base.push({ title: '应成交价 = 开盘 ± 滑点', key: 'expected_price', render: (r) => r.open == null ? '—' : `${r.open} ${r.qty > 0 ? '+' : '−'} ${r.slippage_ticks} × ${r.tick} = ${r.expected_price}` })
    base.push({ title: '实际成交价', key: 'price', width: 96, align: 'right' })
    base.push({ title: '一致', key: 'price_ok', width: 56, align: 'center', render: (r) => ok(r.price_ok) })
  } else {
    base.push({ title: '应成交价 = 开盘 ×（1 ± 0.05%）', key: 'expected_price', render: (r) => r.open == null ? '—' : `${r.open.toFixed(2)} × ${r.qty > 0 ? '1.0005' : '0.9995'} = ${r.expected_price.toFixed(4)}` })
    base.push({ title: '实际成交价', key: 'price', width: 92, align: 'right', render: (r) => r.price.toFixed(4) })
    base.push({ title: '手续费 = 佣金 + 印花税', key: 'fee', render: (r) => `max(${yuan(r.amount)} × 0.025%, 5) + ${r.stamp ? `${yuan(r.amount)} × ${(r.stamp_rate * 100).toFixed(2)}%` : '0'} = ${r.expected_fee.toFixed(2)}（记录 ${r.fee.toFixed(2)}）` })
    base.push({ title: '一致', key: 'ok', width: 56, align: 'center', render: (r) => ok(r.price_ok && r.fee_ok) })
  }
  return base
})
</script>

<template>
  <div class="audit">
    <p class="lead">
      回测结果不需要"相信"，可以自己验证。下面三项核验都<b>不依赖回测引擎</b>：第一项由你的浏览器用每日净值重新计算；第二、三项由服务器直接读取原始行情文件和成交记录从头重算。
    </p>

    <section class="card-s">
      <h4><Calculator :size="15" /> 一、指标复算（浏览器独立计算）
        <span class="badge" :class="allMetricsOk ? 'good' : 'bad'">{{ allMetricsOk ? '全部一致' : '有差异' }}</span></h4>
      <table class="tbl">
        <thead><tr><th>指标</th><th>公式</th><th>回测引擎</th><th>浏览器复算</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in metricRows" :key="r.label">
            <td>{{ r.label }}</td><td class="muted">{{ r.formula }}</td><td class="num">{{ r.eng }}</td><td class="num">{{ r.web }}</td>
            <td><CircleCheck v-if="r.ok" :size="15" class="ok-ic" /><CircleX v-else :size="15" class="bad-ic" /></td>
          </tr>
        </tbody>
      </table>
      <p class="hint">你也可以点报告右上角「导出数据」，用 Excel 打开「每日净值」自己算一遍。</p>
    </section>

    <NSpin :show="loading">
      <div v-if="failed" class="muted">核验数据加载失败：{{ failed }}</div>
      <div v-else-if="audit && !audit.supported" class="muted card-s">{{ audit.reason }}</div>
      <template v-else-if="audit">
        <section class="card-s">
          <h4><Scale :size="15" /> 二、规则核对与账本对账（服务器独立重算）</h4>
          <div v-for="c in audit.checks" :key="c.name" class="check">
            <CircleCheck v-if="c.ok" :size="16" class="ok-ic" /><CircleX v-else :size="16" class="bad-ic" />
            <span>{{ c.name }}</span><b>{{ c.detail }}</b>
          </div>
          <div v-if="audit.reconcile" class="ledger">
            <div class="l-row"><span>期初资金</span><b>{{ yuan(audit.reconcile.initial) }} 元</b></div>
            <div class="l-row"><span>− 买入金额合计</span><b>{{ yuan(audit.reconcile.buy) }}</b></div>
            <div class="l-row"><span>+ 卖出金额合计</span><b>{{ yuan(audit.reconcile.sell) }}</b></div>
            <div class="l-row"><span>− 手续费与印花税合计</span><b>{{ yuan(audit.reconcile.fees) }}</b></div>
            <div class="l-row"><span>+ 现金分红合计</span><b>{{ yuan(audit.reconcile.dividends) }}</b></div>
            <div class="l-row"><span>+ 期末持仓市值（{{ audit.reconcile.holdings.length }} 只 × {{ audit.reconcile.date }} 收盘价）</span><b>{{ yuan(audit.reconcile.holdings_value) }}</b></div>
            <div class="l-row sum"><span>= 重算的期末权益</span><b>{{ yuan(audit.reconcile.computed) }}</b></div>
            <div class="l-row"><span>回测报告的期末权益</span><b>{{ yuan(audit.reconcile.reported) }}</b></div>
            <div class="l-row diff" :class="{ bad: Math.abs(audit.reconcile.diff) >= 1 }"><span>差额</span><b>{{ Math.abs(audit.reconcile.diff) < 0.005 ? '0.00' : audit.reconcile.diff.toFixed(2) }} 元</b></div>
          </div>
          <p v-else class="hint">期货按逐日盯市结算，权益对账见测试报告中的"引擎交叉验证"；这里核对每一笔成交价。</p>
        </section>

        <section class="card-s">
          <h4><ScrollText :size="15" /> 三、逐笔成交核对 <span class="muted small">（共 {{ audit.total_fills }} 条记录，展示前 {{ audit.rows.length }} 笔交易）</span></h4>
          <p class="hint">
            怎么自己核对：打开同花顺、东方财富等任意行情软件，找到这只{{ isFut ? '合约' : '股票' }}在该日的<b>{{ isFut ? '开盘价' : '开盘价（选择"不复权"）' }}</b>，应与"当日开盘价"一致；再用计算器按公式算一遍成交价和手续费。
          </p>
          <NDataTable :columns="fillCols" :data="audit.rows" size="small" :pagination="{ pageSize: 10 }" :scroll-x="980" />
        </section>
      </template>
    </NSpin>
  </div>
</template>

<style scoped>
.audit { display: flex; flex-direction: column; gap: 14px; }
.lead { margin: 0; font-size: 13px; color: var(--text-2); line-height: 1.7; background: var(--primary-soft); padding: 10px 14px; border-radius: 10px; }
.card-s { padding: 14px 16px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface); }
h4 { display: flex; align-items: center; gap: 6px; margin: 0 0 10px; font-size: 14px; }
h4 svg { color: var(--primary); }
.badge { margin-left: auto; font-size: 11.5px; padding: 1px 9px; border-radius: 999px; }
.badge.good { color: var(--t-green); background: var(--t-green-soft); }
.badge.bad { color: var(--up); background: var(--up-soft); }
.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tbl th, .tbl td { padding: 6px 8px; border-bottom: 1px solid var(--border); text-align: left; }
.tbl th { color: var(--text-3); font-weight: 600; }
.num { font-variant-numeric: tabular-nums; text-align: right; }
.muted { color: var(--text-3); }
.small { font-size: 12px; font-weight: 400; }
.hint { font-size: 12px; color: var(--text-3); margin: 8px 0 0; line-height: 1.6; }
.check { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 4px 0; }
.check b { margin-left: auto; font-weight: 600; }
.ledger { margin-top: 10px; border-radius: 10px; background: var(--surface-2); padding: 8px 14px; font-size: 13px; }
.l-row { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; font-variant-numeric: tabular-nums; }
.l-row span { color: var(--text-2); }
.l-row.sum { border-top: 1px dashed var(--border-strong); margin-top: 4px; padding-top: 7px; }
.l-row.diff b { color: var(--t-green); }
.l-row.diff.bad b { color: var(--up); }
:deep(.ok-ic) { color: var(--t-green); }
:deep(.bad-ic) { color: var(--up); }
</style>
