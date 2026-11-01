<script setup lang="ts">
import EmptyChart from '@/components/common/EmptyChart.vue'
import { Layers, Play, Plus, X } from 'lucide-vue-next'
import { NButton, NInputNumber, NRadioButton, NRadioGroup, NSelect, NSpin, NSwitch, useMessage } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { api, cacheBacktest, type BacktestConfig, type BacktestPayload } from '@/api/client'
import ConfigForm from '@/components/common/ConfigForm.vue'
import BacktestReport from '@/components/report/BacktestReport.vue'
import { useCatalog } from '@/stores/catalog'

const toast = useMessage()
const catalog = useCatalog()
const comps = ref<{ strategy: string | null; weight: number }[]>([
  { strategy: 'dual_ma_stock', weight: 50 },
  { strategy: 'momentum_stock', weight: 50 },
])
const equal = ref(true)
const rebalance = ref<'none' | 'M' | 'Q'>('M')
const config = ref<BacktestConfig>({ start: '2022-01-01', end: '2025-06-30', initial_capital: 1e7, benchmarks: ['000300', '000905', '399006'] })
const running = ref(false)
const result = ref<BacktestPayload | null>(null)

const options = computed(() => {
  const g = (label: string, f: (s: any) => boolean) => ({ type: 'group', label, key: label, children: catalog.strategies.filter(f).map((s) => ({ label: s.name, value: s.id })) })
  return [g('股票策略', (s) => s.category === 'stock' && !s.derived), g('期货 CTA 策略', (s) => s.category === 'futures' && !s.derived), g('我的衍生策略', (s) => s.derived)].filter((x) => x.children.length)
})
const total = computed(() => comps.value.reduce((a, c) => a + (c.weight || 0), 0))
const hasFutures = computed(() => comps.value.some((c) => c.strategy && catalog.byId(c.strategy)?.category === 'futures'))

const PRESETS = [
  { name: '趋势 + 动量（股票）', items: ['dual_ma_stock', 'momentum_stock'] },
  { name: '趋势 + 均值回归（期货）', items: ['turtle_futures', 'mean_reversion_futures'] },
  { name: '股票 + 期货 CTA', items: ['dividend_rotation', 'trend_cta_futures'] },
  { name: '红利 + 行业轮动 + 风险平价', items: ['dividend_rotation', 'industry_rotation', 'risk_parity_stock'] },
]
function usePreset(p: (typeof PRESETS)[number]) {
  comps.value = p.items.map((s) => ({ strategy: s, weight: Math.round(100 / p.items.length) }))
  equal.value = true
  if (p.items.some((s) => catalog.byId(s)?.category === 'futures') && config.value.start < '2020-01-01') config.value = { ...config.value, start: '2020-01-01' }
}

async function run() {
  const valid = comps.value.filter((c) => c.strategy)
  if (valid.length < 2) return toast.warning('至少选择两个策略')
  if (!equal.value && total.value <= 0) return toast.warning('权重之和必须大于 0')
  running.value = true
  try {
    const p = await api.post<BacktestPayload>('/api/backtests/portfolio', {
      components: valid.map((c) => ({ strategy: c.strategy, weight: equal.value ? null : c.weight })),
      rebalance: rebalance.value,
      config: config.value,
    })
    cacheBacktest(p)
    result.value = p
    toast.success(`组合回测完成，用时 ${p.elapsed.toFixed(1)} 秒`)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    running.value = false
  }
}
onMounted(() => catalog.load().catch(() => {}))
</script>

<template>
  <div class="lab">
    <aside class="side card">
      <div class="side-head"><Layers :size="17" /> 组合实验室</div>
      <div class="side-body">
        <label class="lbl">快速组合</label>
        <div class="presets">
          <button v-for="p in PRESETS" :key="p.name" class="preset" @click="usePreset(p)">{{ p.name }}</button>
        </div>

        <div class="lbl row">
          <span>子策略（{{ comps.length }}）</span>
          <span class="eq">等权 <NSwitch v-model:value="equal" size="small" /></span>
        </div>
        <div v-for="(c, i) in comps" :key="i" class="comp">
          <NSelect v-model:value="c.strategy" :options="options as any" filterable size="small" placeholder="选择策略" />
          <NInputNumber v-if="!equal" v-model:value="c.weight" :min="0" :max="100" size="small" style="width: 92px"><template #suffix>%</template></NInputNumber>
          <span v-else class="w num">{{ (100 / comps.length).toFixed(0) }}%</span>
          <button class="rm" :disabled="comps.length <= 2" title="移除" @click="comps.splice(i, 1)"><X :size="14" /></button>
        </div>
        <div v-if="!equal" class="muted total" :class="{ off: total !== 100 }">权重合计 {{ total }}%{{ total !== 100 ? '，会按比例归一化' : '' }}</div>
        <NButton dashed size="small" :disabled="comps.length >= 8" @click="comps.push({ strategy: null, weight: 0 })"><template #icon><Plus :size="14" /></template>添加子策略</NButton>

        <label class="lbl">组合再平衡</label>
        <NRadioGroup v-model:value="rebalance" size="small">
          <NRadioButton value="M">每月</NRadioButton>
          <NRadioButton value="Q">每季度</NRadioButton>
          <NRadioButton value="none">不调仓</NRadioButton>
        </NRadioGroup>
        <p class="muted hint">再平衡把各子策略的资金占比调回目标权重；不调仓时权重会随表现漂移</p>

        <ConfigForm v-model="config" :category="hasFutures ? 'futures' : 'stock'" />
      </div>
      <div class="side-foot">
        <NButton type="primary" block size="large" :loading="running" @click="run"><template #icon><Play :size="16" /></template>开始组合回测</NButton>
      </div>
    </aside>
    <section class="result">
      <NSpin :show="running" description="正在回测各子策略并合成组合…">
        <BacktestReport v-if="result" :key="result.id" :data="result" />
        <div v-else class="empty card">
          <EmptyChart />
          <h3>把多个策略组合在一起</h3>
          <p class="muted">相关性低的策略组合后，组合的波动和回撤往往小于单个策略——这就是分散化。回测后可以在「组合分析」中查看相关系数、分散化比率和风险贡献。</p>
        </div>
      </NSpin>
    </section>
  </div>
</template>

<style scoped>
.lab { display: flex; gap: 18px; padding: 20px 24px 40px; align-items: flex-start; max-width: 1640px; margin: 0 auto; }
.side { width: 380px; flex-shrink: 0; position: sticky; top: 20px; max-height: calc(100vh - 40px); display: flex; flex-direction: column; overflow: hidden; }
.side-head { display: flex; align-items: center; gap: 8px; padding: 14px 18px; font-weight: 650; border-bottom: 1px solid var(--border); color: var(--primary-ink); }
.side-body { padding: 4px 18px 16px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.side-foot { padding: 12px 18px; border-top: 1px solid var(--border); }
.lbl { font-size: 12.5px; font-weight: 550; color: var(--text-2); margin-top: 10px; }
.lbl.row { display: flex; justify-content: space-between; align-items: center; }
.eq { display: inline-flex; align-items: center; gap: 6px; font-weight: 400; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; }
.preset { border: 1px solid var(--border); background: var(--surface-2); color: var(--text-2); font-size: 12px; padding: 3px 10px; border-radius: 999px; cursor: pointer; font-family: inherit; }
.preset:hover { border-color: var(--primary); color: var(--primary); }
.comp { display: flex; align-items: center; gap: 6px; }
.w { width: 44px; text-align: right; font-size: 12.5px; color: var(--text-2); }
.rm { border: none; background: none; color: var(--text-3); cursor: pointer; padding: 4px; border-radius: 6px; display: grid; }
.rm:hover:not(:disabled) { background: var(--surface-3); color: var(--up); }
.rm:disabled { opacity: 0.3; cursor: default; }
.total { font-size: 12px; }
.total.off { color: var(--warn); }
.hint { font-size: 11.5px; margin: 2px 0 0; }
.result { flex: 1; min-width: 0; }
.empty { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 90px 40px; gap: 6px; }
.empty h3 { margin: 10px 0 0; font-size: 16px; }
.empty p { max-width: 480px; font-size: 13px; }
@media (max-width: 1000px) { .lab { flex-direction: column; } .side { width: 100%; position: static; max-height: none; } }
</style>
