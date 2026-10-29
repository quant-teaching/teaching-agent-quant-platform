<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import { NResult, NSpin } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getBacktest, type BacktestPayload } from '@/api/client'
import BacktestReport from '@/components/report/BacktestReport.vue'
import { useCatalog } from '@/stores/catalog'

const route = useRoute()
const catalog = useCatalog()
const data = ref<BacktestPayload | null>(null)
const error = ref('')
onMounted(async () => {
  catalog.load().catch(() => {})
  try {
    data.value = await getBacktest(route.params.id as string)
    document.title = `${data.value.title} · 回测报告`
  } catch (e: any) {
    error.value = e.message
  }
})
</script>

<template>
  <div class="page">
    <RouterLink to="/history" class="back"><ArrowLeft :size="15" /> 回测记录</RouterLink>
    <NResult v-if="error" status="404" title="找不到这次回测" :description="error" />
    <NSpin v-else :show="!data">
      <BacktestReport v-if="data" :data="data" />
      <div v-else style="height: 400px" />
    </NSpin>
  </div>
</template>

<style scoped>
.back { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: var(--text-3); margin-bottom: 12px; }
.back:hover { color: var(--primary); }
</style>
