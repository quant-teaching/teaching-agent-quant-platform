<script setup lang="ts">
// 通用搜索框：聚焦时发光描边、图标变色；有内容时显示清除按钮和结果数；
// hotkey 为 true 时按 / 或 Ctrl+K 聚焦，Esc 清空并失焦；上下键和回车交给父组件处理键盘选择。
import { Search, X } from 'lucide-vue-next'
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{ placeholder?: string; count?: number | null; hotkey?: boolean; size?: 'sm' | 'md'; loading?: boolean }>(),
  { placeholder: '搜索', count: null, hotkey: false, size: 'md', loading: false })
const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ enter: []; move: [d: number] }>()
const el = ref<HTMLInputElement | null>(null)
const focused = ref(false)
const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform)

function focus() { el.value?.focus(); el.value?.select() }
function clear() { model.value = ''; el.value?.focus() }
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { if (model.value) model.value = ''; else el.value?.blur() }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); emit('move', e.key === 'ArrowDown' ? 1 : -1) }
  else if (e.key === 'Enter' && !e.isComposing) emit('enter')
}
function onGlobal(e: KeyboardEvent) {
  const typing = (e.target as HTMLElement)?.closest?.('input, textarea, [contenteditable]')
  if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) { e.preventDefault(); focus() }
  else if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); focus() }
}
onMounted(() => { if (props.hotkey) window.addEventListener('keydown', onGlobal) })
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobal))
defineExpose({ focus })
</script>

<template>
  <label class="sbox" :class="[size, { focused, filled: !!model }]">
    <Search class="ic" :size="size === 'sm' ? 14 : 16" />
    <input
      ref="el" v-model="model" :placeholder="placeholder" type="text" spellcheck="false" autocomplete="off"
      @focus="focused = true" @blur="focused = false" @keydown="onKey"
    />
    <span v-if="loading" class="spin" />
    <Transition name="sb-pop">
      <span v-if="model && count !== null && !loading" :key="count" class="count" :class="{ zero: !count }">{{ count }}</span>
    </Transition>
    <Transition name="sb-pop">
      <button v-if="model" type="button" class="clear" title="清空（Esc）" @mousedown.prevent @click="clear"><X :size="13" /></button>
      <kbd v-else-if="hotkey && !focused" class="kbd">{{ isMac ? '⌘K' : '/' }}</kbd>
    </Transition>
  </label>
</template>

<style scoped>
.sbox {
  position: relative; display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 10px 0 12px; border-radius: 11px;
  background: var(--surface); border: 1px solid var(--border); cursor: text;
  transition: border-color 0.2s, box-shadow 0.25s, background 0.2s;
}
.sbox.sm { height: 34px; border-radius: 10px; padding: 0 8px 0 10px; gap: 7px; }
.sbox:hover { border-color: color-mix(in srgb, var(--primary) 35%, var(--border)); }
.sbox.focused { border-color: var(--primary); box-shadow: 0 0 0 4px var(--primary-soft); }
.ic { flex-shrink: 0; color: var(--text-3); transition: color 0.2s, transform 0.3s var(--ease-spring); }
.sbox.focused .ic { color: var(--primary); transform: scale(1.1) rotate(-8deg); }
input { flex: 1; min-width: 0; border: none; outline: none; background: transparent; color: var(--text-1); font: inherit; font-size: 13.5px; }
.sm input { font-size: 13px; }
input::placeholder { color: var(--text-3); }
.count {
  flex-shrink: 0; min-width: 20px; padding: 1px 7px; border-radius: 999px; font-size: 11px; font-weight: 600; text-align: center;
  background: var(--primary-soft); color: var(--primary-ink); font-variant-numeric: tabular-nums;
}
.count.zero { background: var(--surface-3); color: var(--text-3); }
.clear {
  flex-shrink: 0; display: grid; place-items: center; width: 20px; height: 20px; border: none; border-radius: 50%;
  background: var(--surface-3); color: var(--text-2); cursor: pointer; transition: background 0.15s, color 0.15s, transform 0.2s;
}
.clear:hover { background: var(--primary-soft); color: var(--primary-ink); transform: rotate(90deg); }
.kbd {
  flex-shrink: 0; font: 600 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--text-3); padding: 3px 6px;
  border: 1px solid var(--border); border-bottom-width: 2px; border-radius: 6px; background: var(--surface-2);
}
.spin { width: 13px; height: 13px; border-radius: 50%; border: 2px solid var(--primary-soft); border-top-color: var(--primary); animation: sb-spin 0.7s linear infinite; flex-shrink: 0; }
@keyframes sb-spin { to { transform: rotate(360deg); } }
.sb-pop-enter-active { transition: opacity 0.18s, transform 0.25s var(--ease-spring); }
.sb-pop-leave-active { transition: opacity 0.12s, transform 0.12s; position: absolute; right: 10px; }
.sb-pop-enter-from, .sb-pop-leave-to { opacity: 0; transform: scale(0.6); }
</style>
