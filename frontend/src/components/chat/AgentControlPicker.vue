<script setup lang="ts">
// 输入框左侧的「智能体控制」：选择工作模式，并在抽屉里决定智能体能用哪些工具、哪些策略、最多回测几次。
// 这些设置由后端在执行工具前强制检查，不只是写在提示词里。
import { Check, ChevronDown, FlaskConical, Hand, ListChecks, RotateCcw, ShieldCheck, SlidersHorizontal, Zap } from 'lucide-vue-next'
import { NButton, NCheckbox, NDrawer, NDrawerContent, NInputNumber, NPopover, NRadioButton, NRadioGroup, NSelect } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import type { AgentMode } from '@/api/chat'
import { MODES, useAgentControl } from '@/stores/agentControl'
import { useCatalog } from '@/stores/catalog'

const store = useAgentControl()
const catalog = useCatalog()
const show = ref(false)
const drawer = ref(false)

onMounted(() => { store.load(); catalog.load().catch(() => {}) })

const ICONS: Record<AgentMode, any> = { auto: Zap, confirm: Hand, plan: ListChecks, research: FlaskConical }
const cur = computed(() => MODES.find((m) => m.key === store.control.mode) ?? MODES[0])

function pick(k: AgentMode) {
  store.control.mode = k
  show.value = false
}

// 工具按用途分组展示
const GROUPS: { label: string; names: string[] }[] = [
  { label: '算法库与参数', names: ['list_strategies', 'get_strategy', 'update_params', 'reset_params', 'save_derived_strategy'] },
  { label: '回测与实验', names: ['run_backtest', 'run_portfolio_backtest', 'compare_params', 'robustness_test', 'get_backtest_detail'] },
  { label: '资料查询', names: ['search_knowledge', 'get_market_info'] },
]
const groups = computed(() => GROUPS.map((g) => ({ ...g, tools: g.names.map((n) => store.toolMeta(n)).filter(Boolean) as any[] })))
const allTools = computed(() => store.meta?.tools.map((t) => t.name) ?? [])
function toggleTool(name: string, on: boolean) {
  const set = new Set(store.control.tools)
  on ? set.add(name) : set.delete(name)
  store.control.tools = allTools.value.filter((n) => set.has(n))
}

const scope = computed({
  get: () => (store.control.strategies ? 'some' : 'all'),
  set: (v: string) => { store.control.strategies = v === 'all' ? null : (store.control.strategies ?? []) },
})
const strategyOptions = computed(() => [
  { type: 'group', label: '股票策略', key: 'stock', children: catalog.strategies.filter((s) => s.category === 'stock' && !s.derived).map((s) => ({ label: s.name, value: s.id })) },
  { type: 'group', label: '期货策略', key: 'futures', children: catalog.strategies.filter((s) => s.category === 'futures' && !s.derived).map((s) => ({ label: s.name, value: s.id })) },
  { type: 'group', label: '我的衍生策略', key: 'derived', children: catalog.strategies.filter((s) => s.derived).map((s) => ({ label: s.name, value: s.id })) },
].filter((g) => g.children.length))

const summary = computed(() => {
  const c = store.control
  const parts = [`工具 ${c.tools.length}/${allTools.value.length}`]
  parts.push(c.strategies?.length ? `限 ${c.strategies.length} 个策略` : '策略不限')
  parts.push(`每轮最多回测 ${c.max_backtests} 次`)
  return parts.join(' · ')
})
</script>

<template>
  <NPopover v-model:show="show" trigger="click" placement="top-start" :show-arrow="false" raw style="padding: 0">
    <template #trigger>
      <button class="trigger" :class="[`tone-${cur.tone}`, { on: show }]" title="智能体工作模式与控制">
        <component :is="ICONS[cur.key]" :size="14" class="ic" />
        <span class="lb">{{ cur.label }}</span>
        <span v-if="store.restricted" class="dot" title="已限制工具或策略范围" />
        <ChevronDown :size="14" class="chev" />
      </button>
    </template>

    <div class="panel">
      <div class="head">谁来做决定？</div>
      <button v-for="m in MODES" :key="m.key" class="mode" :class="[`tone-${m.tone}`, { sel: store.control.mode === m.key }]" @click="pick(m.key)">
        <span class="m-ic"><component :is="ICONS[m.key]" :size="16" /></span>
        <span class="m-txt"><b>{{ m.label }}</b><span>{{ m.desc }}</span></span>
        <Check v-if="store.control.mode === m.key" :size="16" class="ok" />
      </button>
      <button class="more" @click="show = false; drawer = true">
        <SlidersHorizontal :size="14" /> 工具、策略范围与回测上限
        <span class="sum">{{ summary }}</span>
      </button>
    </div>
  </NPopover>

  <NDrawer v-model:show="drawer" :width="440" placement="right" class="ctl-drawer">
    <NDrawerContent title="智能体控制" closable>
      <p class="intro"><ShieldCheck :size="14" /> 这里的设置由平台在执行每个工具之前强制检查：智能体即使想调用被你禁用的工具或范围外的策略，也只会收到拒绝。</p>

      <section>
        <h4>工作模式</h4>
        <div class="modes">
          <button v-for="m in MODES" :key="m.key" class="mode small" :class="[`tone-${m.tone}`, { sel: store.control.mode === m.key }]" @click="store.control.mode = m.key">
            <span class="m-ic"><component :is="ICONS[m.key]" :size="15" /></span>
            <span class="m-txt"><b>{{ m.label }}</b><span>{{ m.desc }}</span></span>
          </button>
        </div>
      </section>

      <section>
        <h4>允许使用的工具 <small>{{ store.control.tools.length }} / {{ allTools.length }}</small>
          <a class="link" @click="store.control.tools = [...allTools]">全部允许</a>
        </h4>
        <div v-for="g in groups" :key="g.label" class="tgroup">
          <div class="tg-label">{{ g.label }}</div>
          <label v-for="t in g.tools" :key="t.name" class="tool">
            <NCheckbox :checked="store.control.tools.includes(t.name)" @update:checked="(v: boolean) => toggleTool(t.name, v)" />
            <span><b>{{ t.label }}</b><span class="td">{{ t.description }}</span></span>
          </label>
        </div>
      </section>

      <section>
        <h4>可以使用的策略</h4>
        <NRadioGroup v-model:value="scope" size="small">
          <NRadioButton value="all">不限制</NRadioButton>
          <NRadioButton value="some">只允许指定策略</NRadioButton>
        </NRadioGroup>
        <NSelect v-if="scope === 'some'" v-model:value="store.control.strategies as any" multiple filterable clearable
          :options="strategyOptions as any" placeholder="选择允许智能体调取和回测的策略" class="sel" max-tag-count="responsive" />
        <p class="hint">适合布置作业："只用双均线和 MACD 完成本次实验"。</p>
      </section>

      <section>
        <h4>预算</h4>
        <div class="row"><span>每轮对话最多回测</span><NInputNumber v-model:value="store.control.max_backtests" :min="1" :max="30" size="small" style="width: 110px"><template #suffix>次</template></NInputNumber></div>
        <div class="row"><span>自主研究最多迭代</span><NInputNumber v-model:value="store.control.max_iterations" :min="1" :max="5" size="small" style="width: 110px"><template #suffix>轮</template></NInputNumber></div>
        <p class="hint">参数对比实验按对比的参数值个数计入回测次数；用完后智能体只能基于已有结果分析。</p>
      </section>

      <template #footer>
        <NButton quaternary size="small" @click="store.reset()"><template #icon><RotateCcw :size="14" /></template>恢复默认</NButton>
        <NButton type="primary" size="small" @click="drawer = false">完成</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.trigger {
  --tone: var(--t-blue);
  display: inline-flex; align-items: center; gap: 5px; height: 32px; padding: 0 9px 0 10px; border-radius: 999px; position: relative;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text-1); font: inherit; font-size: 12.5px; cursor: pointer;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
}
.trigger:hover, .trigger.on { border-color: color-mix(in srgb, var(--tone) 45%, var(--border)); background: var(--surface); box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 14%, transparent); }
.ic { color: var(--tone); flex-shrink: 0; }
.lb { font-weight: 600; white-space: nowrap; }
.chev { color: var(--text-3); transition: transform 0.2s; }
.trigger.on .chev { transform: rotate(180deg); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); }
.tone-blue { --tone: var(--t-blue); --tone-soft: var(--t-blue-soft); }
.tone-amber { --tone: var(--t-amber); --tone-soft: var(--t-amber-soft); }
.tone-violet { --tone: var(--t-violet); --tone-soft: var(--t-violet-soft); }
.tone-teal { --tone: var(--t-teal); --tone-soft: var(--t-teal-soft); }

.panel { width: 360px; max-width: calc(100vw - 24px); padding: 8px; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); box-shadow: 0 18px 40px rgba(16, 24, 40, 0.18); animation: pop 0.22s var(--ease-out) both; }
.head { padding: 4px 8px 8px; font-size: 12px; font-weight: 650; color: var(--text-3); letter-spacing: 0.5px; }
.mode {
  display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 9px 10px; margin-bottom: 4px; text-align: left; border-radius: 11px;
  border: 1px solid transparent; background: none; font: inherit; color: var(--text-1); cursor: pointer; transition: background 0.15s, border-color 0.2s;
}
.mode:hover { background: var(--surface-2); }
.mode.sel { border-color: color-mix(in srgb, var(--tone) 50%, var(--border)); background: linear-gradient(135deg, var(--tone-soft), transparent 75%); }
.m-ic { width: 30px; height: 30px; flex-shrink: 0; border-radius: 9px; display: grid; place-items: center; color: var(--tone); background: var(--tone-soft); transition: transform 0.3s var(--ease-spring); }
.mode:hover .m-ic { transform: scale(1.08) rotate(-6deg); }
.mode.sel .m-ic { color: #fff; background: var(--tone); }
.m-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; font-size: 12px; color: var(--text-2); line-height: 1.5; }
.m-txt b { font-size: 13.5px; color: var(--text-1); }
.ok { color: var(--tone); flex-shrink: 0; margin-top: 6px; }
.more { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; width: 100%; margin-top: 4px; padding: 9px 10px; border: 0; border-top: 1px solid var(--border); background: none; font: inherit; font-size: 12.5px; color: var(--primary-ink); cursor: pointer; text-align: left; border-radius: 0 0 8px 8px; }
.more:hover { background: var(--surface-2); }
.sum { width: 100%; font-size: 11.5px; color: var(--text-3); }

.intro { display: flex; gap: 6px; font-size: 12.5px; color: var(--text-2); background: var(--primary-soft); padding: 8px 10px; border-radius: 9px; margin: 0 0 14px; line-height: 1.6; }
.intro svg { flex-shrink: 0; margin-top: 3px; color: var(--primary); }
section { margin-bottom: 18px; }
h4 { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: 13.5px; }
h4 small { font-weight: 500; color: var(--text-3); }
.link { margin-left: auto; font-size: 12px; font-weight: 500; color: var(--primary); cursor: pointer; }
.modes { display: flex; flex-direction: column; gap: 2px; }
.mode.small { padding: 7px 9px; border: 1px solid var(--border); margin-bottom: 4px; }
.tgroup { margin-bottom: 8px; }
.tg-label { font-size: 11.5px; font-weight: 650; color: var(--text-3); margin: 6px 0 2px; }
.tool { display: flex; gap: 8px; padding: 5px 6px; border-radius: 8px; cursor: pointer; font-size: 13px; }
.tool:hover { background: var(--surface-2); }
.tool > span { display: flex; flex-direction: column; }
.td { font-size: 11.5px; color: var(--text-3); line-height: 1.5; }
.sel { margin-top: 8px; }
.hint { font-size: 11.5px; color: var(--text-3); margin: 6px 0 0; }
.row { display: flex; align-items: center; justify-content: space-between; font-size: 13px; margin-bottom: 8px; }
</style>
