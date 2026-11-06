<script setup lang="ts">
import { Activity, ArrowLeftRight, BarChart3, BookOpen, Boxes, ChartLine, Coins, Gauge, Layers, Library, RefreshCw, Repeat, Rocket, Scale, Search, ShieldCheck, SlidersHorizontal, Sparkles, Timer, TrendingUp, Wheat, Zap } from 'lucide-vue-next'
import { NInput, NRadioButton, NRadioGroup, NSpin } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import CountUp from '@/components/common/CountUp.vue'
import PageHero from '@/components/common/PageHero.vue'
import { useCatalog } from '@/stores/catalog'
import { universeLabel } from '@/utils/format'

const catalog = useCatalog()
const loading = ref(true)
const cat = ref<'all' | 'stock' | 'futures' | 'derived'>('all')
const q = ref('')
const group = ref('all')

onMounted(async () => {
  await catalog.load(true).catch(() => {})
  loading.value = false
})

const list = computed(() => {
  const k = q.value.trim().toLowerCase()
  return catalog.strategies.filter((s) => {
    if (cat.value === 'derived' && !s.derived) return false
    if (cat.value === 'stock' && (s.category !== 'stock' || s.derived)) return false
    if (cat.value === 'futures' && (s.category !== 'futures' || s.derived)) return false
    if (group.value !== 'all' && styleGroup(s.style) !== group.value) return false
    if (!k) return true
    return [s.name, s.style, s.summary, s.id, ...s.aliases].some((x) => x.toLowerCase().includes(k))
  })
})
const counts = computed(() => ({
  all: catalog.strategies.length,
  stock: catalog.strategies.filter((s) => s.category === 'stock' && !s.derived).length,
  futures: catalog.strategies.filter((s) => s.category === 'futures' && !s.derived).length,
  derived: catalog.strategies.filter((s) => s.derived).length,
}))
const paramCount = computed(() => catalog.strategies.filter((s) => !s.derived).reduce((n, s) => n + s.params.length, 0))

// 按策略风格挑一个图标，卡片左上角和右下角水印使用
const STYLE_ICONS: [string, any][] = [
  ['低波动', ShieldCheck], ['波动率', Gauge], ['量价', BarChart3], ['期限结构', Layers], ['择时', Timer],
  ['套利', ArrowLeftRight], ['轮动', RefreshCw], ['多因子', Boxes], ['动量', Rocket], ['突破', Zap],
  ['均值回归', Repeat], ['反转', Repeat], ['震荡', Activity], ['配置', Scale], ['红利', Coins], ['价值', Coins], ['趋势', TrendingUp],
]
const styleIcon = (style: string) => STYLE_ICONS.find(([k]) => style.includes(k))?.[1] ?? ChartLine

// 按"赚什么钱"把风格归成几大类，便于在策略较多时快速筛选
const GROUPS: { key: string; label: string; words: string[] }[] = [
  { key: 'arb', label: '套利', words: ['套利'] },
  { key: 'alloc', label: '配置与波动率', words: ['配置', '波动率', '期限结构'] },
  { key: 'select', label: '选股与轮动', words: ['截面', '多因子', '轮动', '红利', '价值'] },
  { key: 'revert', label: '均值回归与震荡', words: ['均值回归', '反转', '震荡', '超买超卖'] },
  { key: 'breakout', label: '突破', words: ['突破'] },
  { key: 'trend', label: '趋势与择时', words: ['趋势', '动量', '择时', '量价'] },
]
const styleGroup = (style: string) => GROUPS.find((g) => g.words.some((w) => style.includes(w)))?.key ?? 'trend'
const groupCounts = computed(() => {
  const base = catalog.strategies.filter((s) => cat.value === 'derived' ? s.derived
    : !s.derived && (cat.value === 'all' || s.category === cat.value))
  const out: Record<string, number> = { all: base.length }
  for (const s of base) out[styleGroup(s.style)] = (out[styleGroup(s.style)] ?? 0) + 1
  return out
})
</script>

<template>
  <div class="page">
    <PageHero title="算法库" tone="violet" :icon="BookOpen" :desc="`${counts.stock} 个股票策略 + ${counts.futures} 个期货 CTA 策略，每个都附有原理说明、可调参数和源码；也可以在对话中说「调出海龟策略」`">
      <div class="hero-stats">
        <div class="hero-stat"><span class="ic-tile tone-violet"><Library :size="16" /></span><div><div class="v"><CountUp :value="String(counts.all)" /></div><div class="l">经典策略</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-blue"><TrendingUp :size="16" /></span><div><div class="v"><CountUp :value="String(counts.stock)" /></div><div class="l">股票策略</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-amber"><Wheat :size="16" /></span><div><div class="v"><CountUp :value="String(counts.futures)" /></div><div class="l">期货 CTA 策略</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-teal"><SlidersHorizontal :size="16" /></span><div><div class="v"><CountUp :value="String(paramCount)" /></div><div class="l">可调参数</div></div></div>
      </div>
    </PageHero>

    <div class="toolbar">
      <NRadioGroup v-model:value="cat">
        <NRadioButton value="all">全部 {{ counts.all }}</NRadioButton>
        <NRadioButton value="stock">股票 {{ counts.stock }}</NRadioButton>
        <NRadioButton value="futures">期货 {{ counts.futures }}</NRadioButton>
        <NRadioButton value="derived">我的衍生策略 {{ counts.derived }}</NRadioButton>
      </NRadioGroup>
      <NInput v-model:value="q" placeholder="搜索名称、风格或别名，如 趋势、均值回归、MACD" clearable style="max-width: 340px">
        <template #prefix><Search :size="15" /></template>
      </NInput>
    </div>

    <div class="chips">
      <button v-for="g in [{ key: 'all', label: '全部思路' }, ...GROUPS]" :key="g.key" class="chip" :class="{ on: group === g.key }"
              :disabled="g.key !== 'all' && !groupCounts[g.key]" @click="group = g.key">
        {{ g.label }}<span class="n">{{ groupCounts[g.key] ?? 0 }}</span>
      </button>
    </div>

    <NSpin :show="loading">
      <div class="grid stagger" :key="cat + q + group">
        <RouterLink v-for="s in list" :key="s.id" :to="`/library/${s.id}`" class="card item">
          <component :is="styleIcon(s.style)" class="watermark" :size="96" :stroke-width="1.2" />
          <div class="top">
            <span class="ic-tile" :class="s.category === 'futures' ? 'tone-amber' : 'tone-blue'"><component :is="styleIcon(s.style)" :size="16" /></span>
            <span class="cat" :class="s.category">{{ s.category === 'futures' ? '期货' : '股票' }}</span>
            <span class="style">{{ s.style }}</span>
            <span v-if="s.derived" class="derived"><Sparkles :size="12" /> 衍生</span>
          </div>
          <h3>{{ s.name }}</h3>
          <p>{{ s.summary }}</p>
          <div class="foot">
            <span>{{ s.params.length }} 个参数</span>
            <span>默认标的：{{ universeLabel(s.default_universe) }}</span>
          </div>
        </RouterLink>
      </div>
      <div v-if="!loading && !list.length" class="muted empty">没有符合条件的策略</div>
    </NSpin>
  </div>
</template>

<style scoped>
.toolbar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: -4px 0 16px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-2); font-size: 13px; cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s, transform 0.2s var(--ease-out); }
.chip:hover:not(:disabled) { border-color: color-mix(in srgb, var(--primary) 50%, var(--border)); color: var(--primary-ink); transform: translateY(-1px); }
.chip.on { background: var(--primary-soft); border-color: color-mix(in srgb, var(--primary) 55%, var(--border)); color: var(--primary-ink); font-weight: 600; }
.chip:disabled { opacity: 0.45; cursor: default; }
.chip .n { font-size: 11px; color: var(--text-3); font-variant-numeric: tabular-nums; }
.chip.on .n { color: inherit; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; }
.item { --tone: var(--t-blue); position: relative; overflow: hidden; padding: 16px 18px; display: flex; flex-direction: column; color: var(--text-1); }
.item::before {
  content: ""; position: absolute; inset: 0 0 auto; height: 3px; background: var(--brand-grad);
  transform: scaleX(0); transform-origin: left; transition: transform 0.4s var(--ease-out);
}
.item::after {
  content: ""; position: absolute; width: 180px; height: 180px; right: -70px; top: -90px; border-radius: 50%;
  background: radial-gradient(closest-side, var(--primary-soft), transparent); opacity: 0; transition: opacity 0.3s;
  pointer-events: none;
}
.item:hover { border-color: color-mix(in srgb, var(--primary) 55%, var(--border)); box-shadow: var(--shadow-md); transform: translateY(-3px); }
.item:hover::before { transform: scaleX(1); }
.item:hover::after { opacity: 1; }
.item:has(.cat.futures) { --tone: var(--t-amber); }
.item::before { background: var(--tone) !important; }
.item:hover h3 { color: var(--tone); }
.watermark { position: absolute; right: -14px; bottom: -14px; color: var(--tone); opacity: 0.06; pointer-events: none;
  transition: transform 0.5s var(--ease-out), opacity 0.3s; }
.item:hover .watermark { opacity: 0.13; transform: rotate(-8deg) scale(1.08); }
.top .ic-tile { transition: transform 0.35s var(--ease-spring); }
.item:hover .top .ic-tile { transform: scale(1.1) rotate(-6deg); }
.item > :not(.watermark) { position: relative; }
h3 { transition: color 0.2s; }
.top { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.cat { padding: 1px 8px; border-radius: 6px; font-weight: 600; }
.cat.stock { background: var(--primary-soft); color: var(--primary-ink); }
.cat.futures { background: var(--warn-soft); color: var(--warn); }
.style { color: var(--text-3); }
.derived { margin-left: auto; display: inline-flex; align-items: center; gap: 3px; color: var(--primary-ink); }
h3 { font-size: 16px; font-weight: 650; margin: 12px 0 4px; }
p { font-size: 13px; color: var(--text-2); margin: 0 0 12px; line-height: 1.6; flex: 1; }
.foot { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--text-3); padding-top: 10px; border-top: 1px solid var(--border); }
.empty { text-align: center; padding: 40px; }
</style>
