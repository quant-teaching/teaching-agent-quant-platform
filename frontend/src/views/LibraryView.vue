<script setup lang="ts">
import { Activity, ArrowLeftRight, BookOpen, Boxes, ChartLine, Coins, Library, RefreshCw, Repeat, Rocket, Scale, Search, SlidersHorizontal, Sparkles, TrendingUp, Wheat, Zap } from 'lucide-vue-next'
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
  ['套利', ArrowLeftRight], ['轮动', RefreshCw], ['多因子', Boxes], ['动量', Rocket], ['突破', Zap],
  ['均值回归', Repeat], ['反转', Repeat], ['震荡', Activity], ['配置', Scale], ['红利', Coins], ['价值', Coins], ['趋势', TrendingUp],
]
const styleIcon = (style: string) => STYLE_ICONS.find(([k]) => style.includes(k))?.[1] ?? ChartLine
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

    <NSpin :show="loading">
      <div class="grid stagger" :key="cat + q">
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
