// 算法库与数据概览缓存
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type MarketOverview, type StrategyInfo } from '@/api/client'

export const useCatalog = defineStore('catalog', () => {
  const strategies = ref<StrategyInfo[]>([])
  const market = ref<MarketOverview | null>(null)
  let loading: Promise<void> | null = null

  async function load(force = false) {
    if (loading && !force) return loading
    loading = (async () => {
      const [s, m] = await Promise.all([
        api.get<StrategyInfo[]>('/api/strategies'),
        market.value && !force ? Promise.resolve(market.value) : api.get<MarketOverview>('/api/market'),
      ])
      strategies.value = s
      market.value = m
    })()
    try {
      await loading
    } catch (e) {
      loading = null
      throw e
    }
    return loading
  }

  function byId(id: string) {
    return strategies.value.find((s) => s.id === id)
  }

  return { strategies, market, load, byId }
})
