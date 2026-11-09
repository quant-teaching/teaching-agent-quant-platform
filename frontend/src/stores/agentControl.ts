// 学生对智能体的控制设置：工作模式、允许的工具、策略范围、回测与迭代上限。记在本机浏览器里，每次对话随请求发送。
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { AgentControl, AgentMode } from '@/api/chat'
import { api } from '@/api/client'

export interface ToolMeta {
  name: string
  label: string
  description: string
  parameters: { properties?: Record<string, any>; required?: string[] }
}
interface Meta { modes: Record<AgentMode, string>; defaults: AgentControl; tools: ToolMeta[] }

export const MODES: { key: AgentMode; label: string; desc: string; tone: string }[] = [
  { key: 'auto', label: '自动执行', desc: '智能体自己决定调用哪些工具，一步到位', tone: 'blue' },
  { key: 'confirm', label: '每步确认', desc: '每次调用工具前先暂停，由你批准、修改参数或拒绝', tone: 'amber' },
  { key: 'plan', label: '先计划后执行', desc: '智能体先列出完整计划，你修改确认后再按计划执行', tone: 'violet' },
  { key: 'research', label: '自主研究', desc: '给出研究目标，智能体自己计划、实验、反思并迭代，最后交研究报告', tone: 'teal' },
]

const KEY = 'agent-control'

export const useAgentControl = defineStore('agentControl', () => {
  const meta = ref<Meta | null>(null)
  const control = ref<AgentControl>({ mode: 'auto', tools: [], strategies: null, max_backtests: 12, max_iterations: 3 })
  let loaded = false

  async function load() {
    if (loaded) return
    loaded = true
    try {
      meta.value = await api.get<Meta>('/api/agent/meta')
    } catch {
      loaded = false
      return
    }
    let saved: Partial<AgentControl> = {}
    try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') } catch { /* 读不到用默认 */ }
    const all = meta.value.tools.map((t) => t.name)
    control.value = {
      ...meta.value.defaults,
      ...saved,
      tools: Array.isArray(saved.tools) ? saved.tools.filter((t) => all.includes(t)) : [...all],
    }
  }

  watch(control, (v) => {
    if (!loaded) return
    try { localStorage.setItem(KEY, JSON.stringify(v)) } catch { /* 不可写时只在本次页面有效 */ }
  }, { deep: true })

  function reset() {
    if (meta.value) control.value = { ...meta.value.defaults, tools: meta.value.tools.map((t) => t.name) }
  }

  const restricted = computed(() => !!meta.value && (control.value.tools.length < meta.value.tools.length || !!control.value.strategies?.length))
  const toolMeta = (name: string) => meta.value?.tools.find((t) => t.name === name)

  return { meta, control, load, reset, restricted, toolMeta }
})
