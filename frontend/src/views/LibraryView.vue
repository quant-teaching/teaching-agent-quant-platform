<script setup lang="ts">
import { Search, Sparkles } from 'lucide-vue-next'
import { NInput, NRadioButton, NRadioGroup, NSpin } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
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
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>算法库</h1>
        <p>{{ counts.stock }} 个股票策略 + {{ counts.futures }} 个期货 CTA 策略，每个都附有原理说明、可调参数和源码；也可以在对话中说「调出海龟策略」</p>
      </div>
    </div>

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
      <div class="grid">
        <RouterLink v-for="s in list" :key="s.id" :to="`/library/${s.id}`" class="card item">
          <div class="top">
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
.item { padding: 16px 18px; display: flex; flex-direction: column; color: var(--text-1); transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s; }
.item:hover { border-color: var(--primary); box-shadow: var(--shadow-md); transform: translateY(-1px); }
.top { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.cat { padding: 1px 8px; border-radius: 6px; font-weight: 600; }
.cat.stock { background: var(--primary-soft); color: var(--primary-ink); }
.cat.futures { background: var(--warn-soft); color: var(--warn); }
.style { color: var(--text-3); }
.derived { margin-left: auto; display: inline-flex; align-items: center; gap: 3px; color: var(--primary-ink); }
h3 { font-size: 16px; font-weight: 650; margin: 10px 0 4px; }
p { font-size: 13px; color: var(--text-2); margin: 0 0 12px; line-height: 1.6; flex: 1; }
.foot { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--text-3); padding-top: 10px; border-top: 1px solid var(--border); }
.empty { text-align: center; padding: 40px; }
</style>
