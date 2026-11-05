<script setup lang="ts">
// 对话页的模型选择：「自动」按模型设置里的主备顺序调用；也可以指定某个渠道的某个模型（失败时仍会按主备顺序兜底）。
// 选择记在本机浏览器里；列表变化导致原选择不存在时回到「自动」。
import { Check, ChevronDown, Cpu, Search, Sparkles } from 'lucide-vue-next'
import { NInput, NPopover } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import type { ModelRef } from '@/api/chat'
import { api } from '@/api/client'

interface Choices {
  auto: { primary: string | null; fallbacks: number }
  groups: { provider_id: number; provider: string; models: string[]; section: 'platform' | 'own' }[]
  platform_allowed: boolean
  own_allowed: boolean
  quota: { limit: number | null; used: number; remaining: number | null } | null
}

const model = defineModel<ModelRef | null>({ default: null })
const KEY = 'chat-model'
const data = ref<Choices | null>(null)
const show = ref(false)
const q = ref('')
const failed = ref(false)

onMounted(async () => {
  try {
    data.value = await api.get<Choices>('/api/llm/choices')
  } catch {
    failed.value = true
    return
  }
  let saved: ModelRef | null = null
  try { saved = JSON.parse(localStorage.getItem(KEY) || 'null') } catch { /* 读不到就用自动 */ }
  const ok = saved && data.value.groups.some((g) => g.provider_id === saved!.provider_id && g.models.includes(saved!.model))
  model.value = ok ? saved : null
})

// 每次打开都刷新一次，让剩余额度保持最新
watch(show, async (v) => {
  if (!v) return
  try { data.value = await api.get<Choices>('/api/llm/choices') } catch { /* 保留旧数据 */ }
})
function pick(v: ModelRef | null) {
  model.value = v
  try { localStorage.setItem(KEY, JSON.stringify(v)) } catch { /* 不可写时只在本次页面有效 */ }
  show.value = false
  q.value = ''
}

const configured = computed(() => !!data.value && (data.value.auto.primary || data.value.groups.length))
const label = computed(() => {
  if (!data.value) return failed.value ? '模型' : '加载中…'
  if (!model.value) return data.value.auto.primary ? 'Auto' : '未配置模型'
  return model.value.model
})
const sub = computed(() => '') // 输入框旁空间有限，只显示模型名
const groups = computed(() => {
  const k = q.value.trim().toLowerCase()
  return (data.value?.groups ?? [])
    .map((g) => ({ ...g, models: k ? g.models.filter((m) => m.toLowerCase().includes(k) || g.provider.toLowerCase().includes(k)) : g.models }))
    .filter((g) => g.models.length)
})
const quotaLine = computed(() => {
  const q = data.value?.quota
  if (!q || q.limit === null) return ''
  return `今日平台模型剩余 ${q.remaining} / ${q.limit} 次`
})
const isSel = (pid: number, m: string) => model.value?.provider_id === pid && model.value?.model === m
</script>

<template>
  <RouterLink v-if="data && !configured" to="/settings?tab=model" class="trigger warn">未配置模型</RouterLink>
  <NPopover v-else v-model:show="show" trigger="click" placement="top-end" :show-arrow="false" raw style="padding: 0">
    <template #trigger>
      <button class="trigger" :class="{ on: show }" title="选择对话使用的模型">
        <Sparkles v-if="!model" :size="14" class="ic auto" />
        <Cpu v-else :size="14" class="ic" />
        <span class="lb">{{ label }}</span>
        <span v-if="sub" class="sb">{{ sub }}</span>
        <ChevronDown :size="14" class="chev" />
      </button>
    </template>

    <div class="panel">
      <button class="auto-card" :class="{ sel: !model }" @click="pick(null)">
        <span class="auto-ic"><Sparkles :size="16" /></span>
        <span class="auto-txt">
          <b>Auto <em>推荐</em></b>
          <span v-if="data?.auto.primary">自动选择可用的模型<template v-if="data.auto.fallbacks">，调用失败时自动切换备用模型</template></span>
          <span v-else>还没有设置主模型，请管理员到「设置 → 模型接口」里选择</span>
        </span>
        <Check v-if="!model" :size="16" class="ok" />
      </button>

      <div class="search">
        <NInput v-model:value="q" size="small" placeholder="搜索模型或渠道" clearable>
          <template #prefix><Search :size="14" /></template>
        </NInput>
      </div>

      <div class="list">
        <div v-for="(g, gi) in groups" :key="g.provider_id" class="grp">
          <div v-if="gi === 0 || groups[gi - 1].section !== g.section" class="sec">{{ g.section === 'own' ? '我的渠道 · 不占额度' : '平台渠道' }}</div>
          <div class="grp-title"><span class="dot" :class="g.section" />{{ g.provider }}<span class="cnt">{{ g.models.length }}</span></div>
          <button v-for="m in g.models" :key="m" class="opt" :class="{ sel: isSel(g.provider_id, m) }"
            @click="pick({ provider_id: g.provider_id, model: m })">
            <span class="m">{{ m }}</span>
            <Check v-if="isSel(g.provider_id, m)" :size="14" class="ok" />
          </button>
        </div>
        <div v-if="!groups.length" class="empty">{{ q ? '没有匹配的模型' : '还没有可选的模型，请管理员在「设置 → 模型接口」中拉取模型列表' }}</div>
      </div>
      <div class="foot">
        <span v-if="quotaLine" class="q" :class="{ empty: data?.quota?.remaining === 0 }">{{ quotaLine }}</span>
        <span v-if="data && !data.platform_allowed" class="q empty">平台模型使用权限已关闭，只能使用自己的渠道</span>
        <span>指定模型调用失败时会自动切换备用模型；</span>
        <RouterLink v-if="data?.own_allowed" to="/settings?tab=mine" @click="show = false">添加自己的模型渠道 →</RouterLink>
      </div>
    </div>
  </NPopover>
</template>

<style scoped>
.trigger {
  display: inline-flex; align-items: center; gap: 5px; max-width: 220px; height: 32px; padding: 0 9px 0 10px; border-radius: 999px;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text-1); font: inherit; font-size: 12.5px; cursor: pointer;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
}
.trigger:hover, .trigger.on { border-color: color-mix(in srgb, var(--primary) 45%, var(--border)); background: var(--surface); box-shadow: 0 0 0 3px var(--primary-soft); }
.trigger.warn { color: var(--warn); background: var(--warn-soft); border-color: transparent; }
.ic { color: var(--primary); flex-shrink: 0; }
.ic.auto { color: var(--t-amber); }
.trigger .lb { font-size: 12.5px; }
.lb { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sb { color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 130px; }
.chev { color: var(--text-3); flex-shrink: 0; transition: transform 0.2s; }
.trigger.on .chev { transform: rotate(180deg); }

.panel {
  width: 340px; max-width: calc(100vw - 24px); border-radius: 14px; overflow: hidden;
  background: var(--surface); border: 1px solid var(--border); box-shadow: 0 18px 40px rgba(16, 24, 40, 0.18);
  animation: pop 0.22s var(--ease-out) both;
}
.auto-card {
  display: flex; align-items: flex-start; gap: 10px; width: calc(100% - 16px); margin: 8px; padding: 10px 12px; text-align: left;
  border-radius: 11px; border: 1px solid var(--border); background: linear-gradient(135deg, var(--t-amber-soft), transparent 70%);
  font: inherit; color: var(--text-1); cursor: pointer; transition: border-color 0.2s;
}
.auto-card:hover { border-color: color-mix(in srgb, var(--t-amber) 50%, var(--border)); }
.auto-card.sel { border-color: var(--t-amber); }
.auto-ic { width: 30px; height: 30px; flex-shrink: 0; border-radius: 9px; display: grid; place-items: center; color: #fff; background: linear-gradient(140deg, #f0b43c, #d98a00); }
.auto-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: var(--text-2); line-height: 1.5; }
.auto-txt b { font-size: 13.5px; color: var(--text-1); }
.auto-txt em { font-style: normal; font-size: 11px; font-weight: 600; padding: 0 6px; margin-left: 4px; border-radius: 999px; color: var(--t-amber); background: var(--t-amber-soft); }
.ok { color: var(--primary); flex-shrink: 0; }
.auto-card .ok { color: var(--t-amber); margin-top: 6px; }
.search { padding: 0 10px 8px; }
.list { max-height: 320px; overflow-y: auto; padding: 0 6px 6px; }
.grp + .grp { margin-top: 6px; }
.grp-title { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px; padding: 6px 8px; font-size: 12px; font-weight: 650; color: var(--text-2); background: var(--surface); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--brand-grad); }
.dot.own { background: var(--t-green); }
.sec { padding: 8px 8px 2px; font-size: 11px; font-weight: 650; letter-spacing: 0.5px; color: var(--text-3); }
.cnt { margin-left: auto; font-size: 11px; font-weight: 500; color: var(--text-3); }
.opt {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 7px 10px 7px 20px; border: 0; border-radius: 8px; background: none;
  font: inherit; font-size: 13px; color: var(--text-1); text-align: left; cursor: pointer; transition: background 0.15s;
}
.opt:hover { background: var(--surface-3); }
.opt.sel { background: var(--primary-soft); color: var(--primary-ink); font-weight: 600; }
.m { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono); font-size: 12.5px; }
.empty { padding: 18px 12px; text-align: center; font-size: 12.5px; color: var(--text-3); }
.foot .q { display: block; font-weight: 600; color: var(--t-teal); margin-bottom: 2px; }
.foot .q.empty { color: var(--up); }
.foot a { color: var(--primary); }
.foot { padding: 8px 12px; font-size: 11.5px; color: var(--text-3); border-top: 1px solid var(--border); background: var(--surface-2); }
@media (max-width: 640px) { .sb { display: none; } .trigger { max-width: 150px; } }
</style>
