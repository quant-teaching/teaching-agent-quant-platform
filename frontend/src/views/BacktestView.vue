<script setup lang="ts">
import { FlaskConical, Play, RotateCcw } from 'lucide-vue-next'
import { NButton, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, cacheBacktest, type BacktestConfig, type BacktestPayload } from '@/api/client'
import ConfigForm from '@/components/common/ConfigForm.vue'
import ParamForm from '@/components/common/ParamForm.vue'
import UniverseSelect from '@/components/common/UniverseSelect.vue'
import BacktestReport from '@/components/report/BacktestReport.vue'
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
      <div class="side-head"><FlaskConical :size="17" /> 回测实验室</div>
      <div class="side-body">
        <label class="lbl">策略</label>
        <NSelect v-model:value="strategyId" :options="options as any" filterable placeholder="选择策略" />
        <p v-if="strategy" class="desc">{{ strategy.summary }}</p>

        <template v-if="strategy">
          <label class="lbl">标的</label>
          <UniverseSelect v-model="universe" :asset-types="strategy.asset_types" :default-universe="strategy.default_universe" />
          <ConfigForm v-model="config" :category="strategy.category" />
          <div class="lbl params-lbl">
            <span>策略参数</span>
            <button class="link" @click="resetParams"><RotateCcw :size="12" /> 恢复默认</button>
          </div>
          <ParamForm v-model="params" :specs="strategy.params" dense />
        </template>
      </div>
      <div class="side-foot">
        <NButton type="primary" block size="large" :loading="running" @click="run"><template #icon><Play :size="16" /></template>开始回测</NButton>
      </div>
    </aside>

    <section class="result">
      <NSpin :show="running" description="正在回测…">
        <BacktestReport v-if="result" :key="result.id" :data="result" />
        <div v-else class="empty card">
          <FlaskConical :size="36" class="muted" />
          <h3>选择策略、设置参数后开始回测</h3>
          <p class="muted">回测引擎在每个交易日收盘生成信号、次日开盘成交，并模拟手续费、印花税、滑点、涨跌停与期货保证金。</p>
        </div>
      </NSpin>
    </section>
  </div>
</template>

<style scoped>
.lab { display: flex; gap: 18px; padding: 20px 24px 40px; align-items: flex-start; max-width: 1640px; margin: 0 auto; }
.side { width: 360px; flex-shrink: 0; position: sticky; top: 20px; max-height: calc(100vh - 40px); display: flex; flex-direction: column; overflow: hidden; }
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
