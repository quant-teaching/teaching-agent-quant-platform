<script setup lang="ts">
import { Award, FlaskConical, History, Layers, MessageSquareText, Trash2, Trophy } from 'lucide-vue-next'
import { NButton, NDataTable, NInput, NPopconfirm, NRadioButton, NRadioGroup, useMessage, type DataTableColumns } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type BacktestRecord } from '@/api/client'
import CountUp from '@/components/common/CountUp.vue'
import PageHero from '@/components/common/PageHero.vue'
import { num, pct, signClass, timeAgo } from '@/utils/format'

const router = useRouter()
const toast = useMessage()
const rows = ref<BacktestRecord[]>([])
const loading = ref(true)
const kind = ref<'all' | 'single' | 'portfolio'>('all')
const q = ref('')

async function load() {
  loading.value = true
  try { rows.value = await api.get('/api/backtests?limit=500') } finally { loading.value = false }
}
async function remove(id: string) {
  await api.del(`/api/backtests/${id}`)
  rows.value = rows.value.filter((r) => r.id !== id)
  toast.success('已删除')
}

// 横幅统计：记录数、对话中发起的次数、最高总收益、最高夏普（只做回顾，不代表未来表现）
const stats = computed(() => {
  const r = rows.value
  const best = (k: string) => r.reduce<BacktestRecord | null>((m, x) => (x.summary[k] != null && (m === null || x.summary[k] > (m.summary[k] ?? -Infinity)) ? x : m), null)
  return { total: r.length, chat: r.filter((x) => x.source === 'chat').length, ret: best('total_return'), sharpe: best('sharpe') }
})
const list = computed(() => rows.value.filter((r) => (kind.value === 'all' || r.kind === kind.value) && (!q.value || r.title.includes(q.value))))
const metric = (key: string, signed = false, ratio = false) => (r: BacktestRecord) => {
  const v = r.summary[key]
  return h('span', { class: 'num ' + (signed ? signClass(v) : '') }, ratio ? num(v) : pct(v, 1, signed))
}
const sorter = (key: string) => (a: BacktestRecord, b: BacktestRecord) => (a.summary[key] ?? -1e9) - (b.summary[key] ?? -1e9)

const cols: DataTableColumns<BacktestRecord> = [
  {
    title: '策略', key: 'title', minWidth: 190, fixed: 'left',
    render: (r) => h('div', { class: 'tcell' }, [
      h('div', { class: 'tname' }, [r.kind === 'portfolio' ? h(Layers, { size: 13 }) : null, r.title]),
      h('div', { class: 'tsub' }, [r.universe, r.source === 'chat' ? h('span', { class: 'src' }, [h(MessageSquareText, { size: 11 }), '对话']) : null]),
    ]),
  },
  { title: '区间', key: 'start', width: 190, render: (r) => h('span', { class: 'num muted' }, `${r.start} ~ ${r.end}`) },
  { title: '总收益率', key: 'tr', width: 100, align: 'right', sorter: sorter('total_return'), render: metric('total_return', true) },
  { title: '年化收益率', key: 'ar', width: 104, align: 'right', sorter: sorter('annual_return'), render: metric('annual_return', true) },
  { title: '最大回撤', key: 'mdd', width: 96, align: 'right', sorter: sorter('max_drawdown'), render: metric('max_drawdown') },
  { title: '夏普', key: 'sharpe', width: 76, align: 'right', sorter: sorter('sharpe'), render: metric('sharpe', false, true) },
  { title: '卡玛', key: 'calmar', width: 76, align: 'right', sorter: sorter('calmar'), render: metric('calmar', false, true) },
  { title: '胜率', key: 'wr', width: 80, align: 'right', render: metric('win_rate') },
  { title: '沪深300年化', key: 'hs', width: 108, align: 'right', render: metric('hs300_annual_return', true) },
  { title: '时间', key: 'created_at', width: 100, render: (r) => h('span', { class: 'muted' }, timeAgo(r.created_at)) },
  {
    title: '', key: 'ops', width: 56, align: 'center',
    render: (r) => h(NPopconfirm, { onPositiveClick: () => remove(r.id) }, {
      trigger: () => h(NButton, { size: 'tiny', quaternary: true, onClick: (e: Event) => e.stopPropagation() }, { icon: () => h(Trash2, { size: 14 }) }),
      default: () => '删除这条回测记录？',
    }),
  },
]
const rowProps = (r: BacktestRecord) => ({ style: 'cursor:pointer', onClick: () => router.push(`/report/${r.id}`) })
onMounted(load)
</script>

<template>
  <div class="page">
    <PageHero title="回测记录" tone="rose" :icon="History" desc="回测实验室、组合实验室和对话中执行的所有回测都保存在这里，点击查看完整报告；表头可排序">
      <div class="hero-stats">
        <div class="hero-stat"><span class="ic-tile tone-rose"><FlaskConical :size="16" /></span><div><div class="v"><CountUp :value="String(stats.total)" /></div><div class="l">回测总数</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-violet"><MessageSquareText :size="16" /></span><div><div class="v"><CountUp :value="String(stats.chat)" /></div><div class="l">来自智能助手</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-amber"><Trophy :size="16" /></span><div><div class="v num" :class="signClass(stats.ret?.summary.total_return)"><CountUp :value="stats.ret ? pct(stats.ret.summary.total_return, 1, true) : '—'" /></div><div class="l" :title="stats.ret?.title">最高总收益 · {{ stats.ret?.title ?? '暂无' }}</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-teal"><Award :size="16" /></span><div><div class="v num"><CountUp :value="stats.sharpe ? num(stats.sharpe.summary.sharpe) : '—'" /></div><div class="l" :title="stats.sharpe?.title">最高夏普 · {{ stats.sharpe?.title ?? '暂无' }}</div></div></div>
      </div>
    </PageHero>
    <div class="toolbar">
      <NRadioGroup v-model:value="kind">
        <NRadioButton value="all">全部 {{ rows.length }}</NRadioButton>
        <NRadioButton value="single">单策略</NRadioButton>
        <NRadioButton value="portfolio">组合</NRadioButton>
      </NRadioGroup>
      <NInput v-model:value="q" placeholder="按策略名搜索" clearable style="max-width: 260px" />
    </div>
    <div class="card">
      <NDataTable :columns="cols" :data="list" :loading="loading" :row-props="rowProps" :pagination="{ pageSize: 20 }" :scroll-x="1180" :bordered="false" />
    </div>
  </div>
</template>

<style scoped>
.toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.card { overflow: hidden; }
:deep(.tname) { display: flex; align-items: center; gap: 5px; font-weight: 600; }
:deep(.tsub) { font-size: 12px; color: var(--text-3); display: flex; gap: 8px; align-items: center; }
:deep(.src) { display: inline-flex; align-items: center; gap: 2px; color: var(--primary-ink); }
</style>
