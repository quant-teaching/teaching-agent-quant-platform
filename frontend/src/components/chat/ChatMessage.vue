<script setup lang="ts">
import { AlertTriangle, Check, ChevronDown, Loader2, Repeat, ShieldAlert, ShieldCheck, Sparkles, X } from 'lucide-vue-next'
import { NTooltip } from 'naive-ui'
import { computed, ref } from 'vue'
import MarkdownView from '@/components/common/MarkdownView.vue'
import ToolCard from './ToolCard.vue'
import type { ToolBlock, UiMessage } from './types'

const props = defineProps<{ msg: UiMessage }>()
const emit = defineEmits<{ open: [id: string] }>()
const collapsed = ref<Record<string, boolean>>({})

// 连续的工具步骤合并成一组展示
const groups = computed(() => {
  const out: ({ type: 'tools'; items: ToolBlock[] } | { type: 'text'; text: string; last: boolean })[] = []
  props.msg.blocks.forEach((b, i) => {
    if (b.kind === 'tool') {
      const last = out[out.length - 1]
      if (last && last.type === 'tools') last.items.push(b)
      else out.push({ type: 'tools', items: [b] })
    } else if (b.text.trim()) {
      out.push({ type: 'text', text: b.text, last: i === props.msg.blocks.length - 1 })
    }
  })
  return out
})
function hasCard(t: ToolBlock) {
  return !!t.card
}
const thinking = computed(() => props.msg.streaming && (!props.msg.blocks.length || props.msg.blocks[props.msg.blocks.length - 1].kind === 'tool'))
</script>

<template>
  <div v-if="msg.role === 'user'" class="row user">
    <div class="bubble">{{ msg.text }}</div>
  </div>

  <div v-else class="row bot">
    <div class="avatar"><Sparkles :size="16" /></div>
    <div class="body">
      <div v-for="sw in msg.switches" :key="sw.to" class="switch">
        <Repeat :size="13" />
        <span>主模型「{{ sw.from }}」不可用（{{ sw.reason }}），已自动切换到备用模型「{{ sw.to }}」</span>
      </div>

      <template v-for="(g, gi) in groups" :key="gi">
        <div v-if="g.type === 'tools'" class="steps">
          <div v-for="t in g.items" :key="t.id" class="step-wrap">
            <button class="step" :class="t.status" @click="collapsed[t.id] = !collapsed[t.id]">
              <Loader2 v-if="t.status === 'running'" :size="13" class="spin" />
              <Check v-else-if="t.status === 'ok'" :size="13" />
              <X v-else :size="13" />
              <span class="step-label">{{ t.label }}</span>
              <ChevronDown v-if="hasCard(t) || t.error" :size="13" class="chev" :class="{ up: !collapsed[t.id] }" />
            </button>
            <div v-if="t.error && !collapsed[t.id]" class="step-err">{{ t.error }}</div>
            <ToolCard v-if="t.card && !collapsed[t.id]" :card="t.card" @open="emit('open', $event)" />
          </div>
        </div>
        <MarkdownView v-else breaks :source="g.text + (msg.streaming && g.last ? ' ▍' : '')" class="text" />
      </template>

      <div v-if="thinking" class="thinking"><span /><span /><span /></div>

      <div v-if="msg.error" class="error"><AlertTriangle :size="14" /> {{ msg.error }}</div>

      <div v-if="msg.disclaimer" class="disclaimer">⚠️ 本结果为教学回测模拟，历史回测不代表未来表现，不构成任何投资建议。</div>

      <div v-if="!msg.streaming && (msg.factCheck || msg.model)" class="foot">
        <NTooltip v-if="msg.factCheck && msg.factCheck.checked > 0" placement="top-start">
          <template #trigger>
            <span class="fc" :class="msg.factCheck.status">
              <ShieldCheck v-if="msg.factCheck.status === 'ok'" :size="13" />
              <ShieldAlert v-else :size="13" />
              {{ msg.factCheck.status === 'ok' ? `数据核验通过 · ${msg.factCheck.checked} 个数字均来自回测结果` : `有 ${msg.factCheck.unmatched.length} 个数字未能核验` }}
            </span>
          </template>
          <template v-if="msg.factCheck.status === 'ok'">回复中的百分数和小数都能在工具返回的回测数据、知识库或你的输入中找到，没有编造的数字。</template>
          <template v-else>以下数字没有出现在工具结果中，请谨慎看待：{{ msg.factCheck.unmatched.join('、') }}</template>
        </NTooltip>
        <span v-if="msg.model" class="model">{{ msg.model }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row { display: flex; gap: 12px; margin: 18px 0; animation: msg-in 0.4s var(--ease-out) both; }
.row.user { transform-origin: right bottom; }
@keyframes msg-in { from { opacity: 0; transform: translateY(10px) scale(0.98); } to { opacity: 1; transform: none; } }
.row.user { justify-content: flex-end; }
.bubble { max-width: 78%; background: var(--brand-grad); color: #fff; padding: 9px 14px; border-radius: 16px 16px 4px 16px; white-space: pre-wrap; word-break: break-word; font-size: 14px; line-height: 1.6; box-shadow: var(--shadow-sm); }
.avatar { width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0; display: grid; place-items: center; background: var(--brand-grad); color: #fff; margin-top: 2px; box-shadow: 0 4px 12px rgba(42, 120, 214, 0.25); }
.body { flex: 1; min-width: 0; }
.text {
  position: relative; margin: 4px 0; padding: 14px 18px 14px 20px; border-radius: 4px 16px 16px 16px;
  background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-sm);
}
.text::before {
  content: ""; position: absolute; left: -1px; top: 14px; bottom: 14px; width: 3px; border-radius: 3px; background: var(--brand-grad);
}
.text + .text { margin-top: 8px; }
.steps { display: flex; flex-direction: column; gap: 4px; margin: 4px 0 8px; }
.step { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; border: 1px solid var(--border); background: var(--surface-2); color: var(--text-2); font-size: 12.5px; padding: 3px 10px; border-radius: 999px; cursor: pointer; font-family: inherit; }
.step { transition: border-color 0.2s, background 0.2s, color 0.2s; }
.step:hover { border-color: var(--border-strong); }
.step-wrap { animation: rise 0.35s var(--ease-out) both; }
.step-wrap > :deep(:not(.step)) { animation: pop 0.4s var(--ease-out) both; }
.step.running { border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); color: var(--primary-ink);
  background: linear-gradient(90deg, var(--surface-2) 30%, var(--primary-soft) 50%, var(--surface-2) 70%) 0 0 / 220% 100%;
  animation: shimmer 1.6s linear infinite; }
.step.ok svg:first-child { animation: pop 0.35s var(--ease-spring) both; }
.disclaimer, .foot { animation: rise 0.4s var(--ease-out) both; }
.step.ok svg:first-child { color: var(--primary); }
.step.error { color: var(--up); }
.step-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chev { transition: transform 0.15s; opacity: 0.6; }
.chev.up { transform: rotate(180deg); }
.step-err { font-size: 12px; color: var(--up); margin: 2px 0 2px 12px; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.thinking { display: flex; gap: 4px; padding: 10px 2px; }
.thinking span { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); animation: blink 1.2s infinite ease-in-out; }
.thinking span:nth-child(2) { animation-delay: 0.15s; }
.thinking span:nth-child(3) { animation-delay: 0.3s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); } 40% { opacity: 1; transform: scale(1); } }
.switch { display: flex; gap: 6px; align-items: flex-start; font-size: 12.5px; color: var(--warn); background: var(--warn-soft); padding: 6px 10px; border-radius: 8px; margin-bottom: 8px; }
.switch svg { flex-shrink: 0; margin-top: 3px; }
.error { display: flex; gap: 6px; align-items: center; color: var(--up); font-size: 13px; margin: 6px 0; }
.disclaimer { font-size: 12.5px; color: var(--text-2); background: var(--surface-2); border: 1px solid var(--border); border-left: 3px solid var(--warn); border-radius: 8px; padding: 8px 12px; margin-top: 10px; }
.foot { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.fc { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; padding: 2px 8px; border-radius: 6px; cursor: help; }
.fc.ok { color: var(--primary-ink); background: var(--primary-soft); }
.fc.warn { color: var(--warn); background: var(--warn-soft); }
.model { font-size: 11.5px; color: var(--text-3); }
</style>
