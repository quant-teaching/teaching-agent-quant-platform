<script setup lang="ts">
import EmptyChart from '@/components/common/EmptyChart.vue'
import { FlaskConical, Grid3x3, Play, RotateCcw } from 'lucide-vue-next'
import { NButton, NDatePicker, NInput, NRadioButton, NRadioGroup, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, cacheBacktest, type BacktestConfig, type BacktestPayload } from '@/api/client'
import ConfigForm from '@/components/common/ConfigForm.vue'
import ParamForm from '@/components/common/ParamForm.vue'
import UniverseSelect from '@/components/common/UniverseSelect.vue'
import BacktestReport from '@/components/report/BacktestReport.vue'
import RobustnessResult from '@/components/report/RobustnessResult.vue'
import { useCatalog } from '@/stores/catalog'

const route = useRoute()
const toast = useMessage()
const catalog = useCatalog()
const strategyId = ref<string | null>(null)
const params = ref<Record<string, any>>({})
const universe = ref('')
const config = ref<BacktestConfig>({ start: '2022-01-01', end: '2025-12-31', initial_capital: 1e7, benchmarks: ['000300', '000905', '399006'] })
const running = ref(false)
const result = ref<BacktestPayload | null>(null)

// 稳健性检验：在参数网格上回测，比较样本内 / 样本外
const mode = ref<'single' | 'robust'>('single')
const rx = ref<string | null>(null)
const ry = ref<string | null>(null)
const rxValues = ref('')
const ryValues = ref('')
const split = ref<string | null>(null)
const metric = ref('sharpe')
const robust = ref<any>(null)
const numericParams = computed(() => (strategy.value?.params ?? []).filter((p) => p.type === 'integer' || p.type === 'number'))
const paramOptions = computed(() => numericParams.value.map((p) => ({ label: `${p.title}（${p.key}）`, value: p.key })))
function suggest(key: string | null) {
  // 以当前值为中心给出 5 个候选取值，学生可以直接修改
  const p = numericParams.value.find((x) => x.key === key)
  if (!p) return ''
  const v = Number(params.value[key!] ?? p.default)
  const int = p.type === 'integer'
  const raw = [0.5, 0.75, 1, 1.5, 2].map((k) => v * k)
  const lo = (p as any).min ?? (p as any).gt ?? -Infinity
  const hi = (p as any).max ?? (p as any).lt ?? Infinity
  const vals = raw.map((x) => (int ? Math.round(x) : Number(x.toPrecision(3)))).filter((x) => x >= lo && x <= hi)
  return [...new Set(vals)].join(', ')
}
watch(rx, (k) => { rxValues.value = suggest(k) })
watch(ry, (k) => { ryValues.value = suggest(k) })
watch(strategyId, () => { rx.value = numericParams.value[0]?.key ?? null; ry.value = null; robust.value = null })
const parseVals = (t: string) => t.split(/[,，\s]+/).filter(Boolean).map(Number).filter((x) => !Number.isNaN(x))
async function runRobust() {
  if (!strategy.value || !rx.value) return toast.warning('请选择要检验的参数')
  running.value = true
  try {
    robust.value = await api.post('/api/research/robustness', {
      strategy: strategy.value.id, params: params.value, universe: universe.value, start: config.value.start, end: config.value.end,
      split: split.value || null, metric: metric.value, x_key: rx.value, x_values: parseVals(rxValues.value),
      y_key: ry.value || null, y_values: ry.value ? parseVals(ryValues.value) : null,
    })
    toast.success(`完成 ${robust.value.backtests} 次回测，用时 ${robust.value.elapsed.toFixed(1)} 秒`)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    running.value = false
  }
}

const strategy = computed(() => (strategyId.value ? catalog.byId(strategyId.value) : undefined))
const options = computed(() => {
  const g = (label: string, f: (s: any) => boolean) => ({ type: 'group', label, key: label, children: catalog.strategies.filter(f).map((s) => ({ label: s.name, value: s.id })) })
  return [g('股票策略', (s) => s.category === 'stock' && !s.derived), g('期货 CTA 策略', (s) => s.category === 'futures' && !s.derived), g('我的衍生策略', (s) => s.derived)].filter((x) => x.children.length)
})

function resetParams() {
  if (strategy.value) params.value = Object.fromEntries(strategy.value.params.map((p) => [p.key, p.default]))
}
watch(strategyId, (id, old) => {
  if (!strategy.value) return
  if (old !== undefined) resetParams()
  universe.value = strategy.value.default_universe
  if (strategy.value.category === 'futures' && config.value.start < '2019-07-01') config.value = { ...config.value, start: '2020-01-01' }
})

async function run() {
  if (!strategy.value) return toast.warning('请先选择策略')
  if (!universe.value) return toast.warning('请选择标的')
  running.value = true
  try {
    const p = await api.post<BacktestPayload>('/api/backtests', { strategy: strategy.value.id, params: params.value, universe: universe.value, config: config.value })
    cacheBacktest(p)
    result.value = p
    toast.success(`回测完成，用时 ${p.elapsed.toFixed(1)} 秒`)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  await catalog.load().catch(() => {})
  const q = route.query
  strategyId.value = (q.strategy as string) || 'dual_ma_stock'
  await Promise.resolve()
  resetParams()
  if (q.params) {
    try { params.value = { ...params.value, ...JSON.parse(q.params as string) } } catch { /* 忽略 */ }
  }
  universe.value = strategy.value?.default_universe ?? ''
})
</script>

<template>
  <div class="lab">
    <aside class="side card">
      <div class="side-head"><FlaskConical :size="17" /> 回测实验室
        <NRadioGroup v-model:value="mode" size="small" class="mode">
          <NRadioButton value="single">单次回测</NRadioButton>
          <NRadioButton value="robust">稳健性检验</NRadioButton>
        </NRadioGroup>
      </div>
      <div class="side-body">
        <label class="lbl">策略</label>
        <NSelect v-model:value="strategyId" :options="options as any" filterable placeholder="选择策略" />
        <p v-if="strategy" class="desc">{{ strategy.summary }}</p>

        <template v-if="strategy">
          <label class="lbl">标的</label>
          <UniverseSelect v-model="universe" :asset-types="strategy.asset_types" :default-universe="strategy.default_universe" />
          <ConfigForm v-model="config" :category="strategy.category" />
          <template v-if="mode === 'robust'">
            <div class="lbl params-lbl"><span>稳健性检验</span></div>
            <p class="desc">在参数网格上逐一回测，按分割日把结果切成样本内（用来"挑参数"）和样本外（用来"检验"），看最优参数换一段时间还灵不灵。</p>
            <label class="lbl">参数一</label>
            <NSelect v-model:value="rx" :options="paramOptions" size="small" />
            <NInput v-model:value="rxValues" size="small" placeholder="取值，用逗号分隔，如 5, 10, 20" />
            <label class="lbl">参数二（可选，做二维热力图）</label>
            <NSelect v-model:value="ry" :options="paramOptions.filter((o) => o.value !== rx)" size="small" clearable placeholder="不选则只检验一个参数" />
            <NInput v-if="ry" v-model:value="ryValues" size="small" placeholder="取值，用逗号分隔" />
            <label class="lbl">样本内 / 样本外分割日</label>
            <NDatePicker v-model:formatted-value="split" value-format="yyyy-MM-dd" type="date" size="small" clearable placeholder="不填取区间前 70%" />
            <label class="lbl">评价指标</label>
            <NSelect v-model:value="metric" size="small" :options="[{ label: '夏普比率', value: 'sharpe' }, { label: '年化收益率', value: 'annual_return' }, { label: '最大回撤', value: 'max_drawdown' }, { label: '卡玛比率', value: 'calmar' }]" />
          </template>
          <div class="lbl params-lbl">
            <span>{{ mode === 'robust' ? '其余参数' : '策略参数' }}</span>
            <button class="link" @click="resetParams"><RotateCcw :size="12" /> 恢复默认</button>
          </div>
          <ParamForm v-model="params" :specs="strategy.params" dense />
        </template>
      </div>
      <div class="side-foot">
        <NButton v-if="mode === 'single'" type="primary" block size="large" :loading="running" @click="run"><template #icon><Play :size="16" /></template>开始回测</NButton>
        <NButton v-else type="primary" block size="large" :loading="running" @click="runRobust"><template #icon><Grid3x3 :size="16" /></template>开始稳健性检验</NButton>
      </div>
    </aside>

    <section v-if="mode === 'robust'" class="result">
      <NSpin :show="running">
        <div v-if="robust" class="card rob-card">
          <div class="rob-head"><Grid3x3 :size="16" /> {{ robust.strategy.name }} · 稳健性检验<span class="muted">{{ robust.backtests }} 次回测 · {{ robust.period[0] }} ~ {{ robust.period[1] }}</span></div>
          <RobustnessResult :data="robust" />
        </div>
        <div v-else class="empty card">
          <EmptyChart />
          <h3>{{ running ? '正在逐组回测…' : '选择要检验的参数和取值，开始稳健性检验' }}</h3>
          <p class="muted">参数调到"过去最好"不代表未来也好。把历史切成两段：前一段挑参数，后一段检验。样本内最优的参数如果到了样本外排名大跌，就是过拟合。</p>
        </div>
      </NSpin>
    </section>
    <section v-else class="result">
      <!-- 已有报告时再次回测：在报告上加遮罩；还没有报告时：空状态卡片本身变成加载状态，避免文字叠在一起 -->
      <NSpin :show="running && !!result" description="正在回测…">
        <BacktestReport v-if="result" :key="result.id" :data="result" />
        <div v-else class="empty card" :class="{ busy: running }">
          <EmptyChart />
          <template v-if="running">
            <h3 class="run-title">正在回测<span class="run-dots"><i /><i /><i /></span></h3>
            <p class="muted">正在加载行情、逐日撮合交易并计算指标，通常只需几秒</p>
            <div class="run-bar"><span /></div>
          </template>
          <template v-else>
            <h3>选择策略、设置参数后开始回测</h3>
            <p class="muted">回测引擎在每个交易日收盘生成信号、次日开盘成交，并模拟手续费、印花税、滑点、涨跌停与期货保证金。</p>
          </template>
        </div>
      </NSpin>
    </section>
  </div>
</template>

<style scoped>
.lab { display: flex; gap: 18px; padding: 20px 24px 40px; align-items: flex-start; max-width: 1640px; margin: 0 auto; }
.side { width: 360px; flex-shrink: 0; position: sticky; top: 20px; max-height: calc(100vh - 40px); display: flex; flex-direction: column; overflow: hidden; }
.mode { margin-left: auto; }
.rob-card { padding: 16px 18px; }
.rob-head { display: flex; align-items: center; gap: 8px; font-weight: 650; margin-bottom: 12px; }
.rob-head .muted { margin-left: auto; font-weight: 400; font-size: 12.5px; }
.side-head { display: flex; align-items: center; gap: 8px; padding: 14px 18px; font-weight: 650; border-bottom: 1px solid var(--border); color: var(--primary-ink); }
.side-body { padding: 4px 18px 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.side-foot { padding: 12px 18px; border-top: 1px solid var(--border); }
.lbl { font-size: 12.5px; font-weight: 550; color: var(--text-2); margin-top: 10px; }
.params-lbl { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border); }
.link { border: none; background: none; color: var(--primary); font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 3px; font-family: inherit; }
.desc { font-size: 12.5px; color: var(--text-3); margin: 4px 0 0; line-height: 1.55; }
.result { flex: 1; min-width: 0; }
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 90px 40px; gap: 6px; }
.empty h3 { margin: 10px 0 0; font-size: 16px; }
.empty p { max-width: 460px; font-size: 13px; }
@media (max-width: 1000px) { .lab { flex-direction: column; } .side { width: 100%; position: static; max-height: none; } }
</style>
