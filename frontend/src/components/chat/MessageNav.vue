<script setup lang="ts">
// 提问导航（对话区左侧，紧挨会话列表）：每条提问一根短线，当前阅读位置的线加长高亮。
// 鼠标靠近时线条按距离放大（类似程序坞），悬停展开提问列表；列表与线条联动，点击跳转到对应提问。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { UiMessage } from './types'

const props = defineProps<{ messages: UiMessage[]; scroller: HTMLElement | null }>()

const items = computed(() => props.messages.filter((m) => m.role === 'user')
  .map((m, i) => ({ key: m.key, no: i + 1, text: (m.text ?? '').replace(/\s+/g, ' ').trim() })))
const active = ref<string | null>(null)
const hovered = ref<string | null>(null) // 列表或线条上正指着的那条
const open = ref(false)
const pointerY = ref<number | null>(null)
const railEl = ref<HTMLElement | null>(null)
const listEl = ref<HTMLElement | null>(null)
let closeTimer: number | undefined
let lockUntil = 0 // 点击跳转后的平滑滚动期间，高亮固定在目标提问上

// 提问很多时压缩间距，导航条总高度不超过可视区域
const RAIL_MAX = 440
const gap = computed(() => Math.max(3, Math.min(10, RAIL_MAX / Math.max(items.value.length, 1) - 2)))
const activeIndex = computed(() => items.value.findIndex((x) => x.key === active.value))

function el(key: string) {
  return props.scroller?.querySelector<HTMLElement>(`[data-mkey="${key}"]`) ?? null
}

/** 线条宽度：基础 10px；当前位置 20px；离鼠标越近越宽（最多 26px） */
const tickEls: HTMLElement[] = [] // 普通数组：只在渲染时读取位置，不需要响应式
function width(i: number, key: string) {
  let w = key === active.value ? 20 : 10
  if (key === hovered.value) w = Math.max(w, 24)
  const t = tickEls[i]
  if (pointerY.value !== null && t) {
    const r = t.getBoundingClientRect()
    const d = Math.abs(r.top + r.height / 2 - pointerY.value)
    w = Math.max(w, 10 + 16 * Math.max(0, 1 - d / 60))
  }
  return w
}

function update() {
  const sc = props.scroller
  if (!sc || !items.value.length) return (active.value = null)
  if (Date.now() < lockUntil) return
  // 以可视区域顶部往下一小段为准：这条线以上最后出现的提问就是正在看的
  const line = sc.getBoundingClientRect().top + Math.min(140, sc.clientHeight * 0.3)
  let cur = items.value[0].key
  for (const it of items.value) {
    const e = el(it.key)
    if (e && e.getBoundingClientRect().top <= line) cur = it.key
  }
  if (sc.scrollHeight - sc.scrollTop - sc.clientHeight < 4) cur = items.value[items.value.length - 1].key // 滚到底
  active.value = cur
}

function jump(key: string) {
  const sc = props.scroller, e = el(key)
  if (!sc || !e) return
  const top = e.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - 16
  active.value = key
  lockUntil = Date.now() + 900
  sc.scrollTo({ top, behavior: 'smooth' })
  e.classList.remove('nav-flash')
  void e.offsetWidth // 重新触发闪烁动画
  e.classList.add('nav-flash')
  window.setTimeout(() => e.classList.remove('nav-flash'), 1500)
}

function enter() {
  window.clearTimeout(closeTimer)
  if (open.value) return
  open.value = true
  nextTick(() => listEl.value?.querySelector('.item.cur')?.scrollIntoView({ block: 'center' }))
}
function leave() {
  pointerY.value = null
  hovered.value = null
  closeTimer = window.setTimeout(() => (open.value = false), 220)
}
function onRailMove(e: MouseEvent) {
  pointerY.value = e.clientY
  // 指着最近的一根线，列表里对应的一条同步高亮
  let best: string | null = null, bd = Infinity
  tickEls.forEach((t, i) => {
    const r = t.getBoundingClientRect()
    const d = Math.abs(r.top + r.height / 2 - e.clientY)
    if (d < bd) { bd = d; best = items.value[i]?.key ?? null }
  })
  hovered.value = best
  if (best) listEl.value?.querySelector(`[data-k="${best}"]`)?.scrollIntoView({ block: 'nearest' })
}

watch(() => props.scroller, (sc, old) => {
  old?.removeEventListener('scroll', update)
  sc?.addEventListener('scroll', update, { passive: true })
  update()
}, { immediate: true })
watch(() => items.value.length, (n) => { tickEls.length = n; nextTick(update) })
onBeforeUnmount(() => props.scroller?.removeEventListener('scroll', update))
</script>

<template>
  <Transition name="nav">
    <nav v-if="items.length >= 2" class="mnav" :class="{ open }" aria-label="提问导航" @mouseenter="enter" @mouseleave="leave">
      <div ref="railEl" class="rail" :style="{ gap: `${gap}px` }" @mousemove="onRailMove" @mouseleave="pointerY = null">
        <TransitionGroup name="tick">
          <button
            v-for="(it, i) in items" :key="it.key" :ref="(x) => { if (x) tickEls[i] = x as HTMLElement }"
            class="tick" :class="{ cur: it.key === active, hov: it.key === hovered }"
            :aria-label="`跳到第 ${it.no} 条提问`" @click="jump(it.key)"
          ><span :style="{ width: `${width(i, it.key)}px` }" /></button>
        </TransitionGroup>
      </div>
      <Transition name="pop">
        <div v-if="open" ref="listEl" class="list">
          <div class="list-head">
            <span>本次对话的提问</span>
            <span class="count">{{ activeIndex + 1 }} / {{ items.length }}</span>
          </div>
          <button
            v-for="(it, i) in items" :key="it.key" :data-k="it.key" class="item"
            :class="{ cur: it.key === active, hov: it.key === hovered }" :style="{ animationDelay: `${Math.min(i, 12) * 18}ms` }"
            @mouseenter="hovered = it.key" @click="jump(it.key)"
          >
            <span class="no">{{ it.no }}</span><span class="txt">{{ it.text || '（空）' }}</span>
          </button>
        </div>
      </Transition>
    </nav>
  </Transition>
</template>

<style scoped>
.mnav { position: absolute; left: 0; top: 50%; transform: translateY(-50%); z-index: 6; display: flex; align-items: center; padding-left: 8px; }

/* 线条导航 */
.rail {
  position: relative; display: flex; flex-direction: column; align-items: flex-start; padding: 12px 8px; max-height: 72vh; overflow: hidden;
  border-radius: 12px; transition: background 0.25s, box-shadow 0.25s;
}
.mnav.open .rail { background: var(--surface); box-shadow: 0 0 0 1px var(--border), 0 6px 18px rgba(15, 23, 42, 0.08); }
.tick { border: none; background: none; padding: 2px 0; cursor: pointer; display: flex; width: 28px; }
.tick span {
  display: block; height: 2px; border-radius: 2px; background: var(--text-3); opacity: 0.4;
  transition: width 0.22s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.2s, background 0.2s, height 0.2s;
}
.mnav.open .tick span { opacity: 0.65; }
.tick.hov span { opacity: 1; background: var(--text-1); }
.tick.cur span { opacity: 1; background: var(--primary); height: 3px; }

/* 提问列表 */
.list {
  position: absolute; left: calc(100% + 6px); top: 50%; transform: translateY(-50%); width: 320px; max-height: min(62vh, 460px); overflow-y: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 6px;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16), 0 2px 6px rgba(15, 23, 42, 0.06); transform-origin: left center;
}
.list-head { position: sticky; top: -6px; display: flex; justify-content: space-between; font-size: 11.5px; color: var(--text-3); padding: 8px 10px 6px; margin: -6px -6px 2px; background: var(--surface); border-bottom: 1px solid var(--border); }
.count { font-variant-numeric: tabular-nums; color: var(--primary); }
.item {
  position: relative; display: flex; gap: 10px; align-items: baseline; width: 100%; text-align: left; border: none; background: none; cursor: pointer;
  padding: 8px 10px; border-radius: 9px; color: var(--text-2); font: inherit; animation: item-in 0.28s var(--ease-out) both;
  transition: background 0.15s, color 0.15s, padding-left 0.2s var(--ease-out);
}
.item::before { content: ''; position: absolute; left: 2px; top: 50%; width: 3px; height: 0; border-radius: 2px; background: var(--primary); transform: translateY(-50%); transition: height 0.2s var(--ease-out); }
.item.hov { background: var(--surface-3); color: var(--text-1); padding-left: 14px; }
.item.cur { color: var(--primary); background: var(--primary-soft); }
.item.cur::before { height: 60%; }
.no { flex-shrink: 0; min-width: 18px; font-size: 11px; color: var(--text-3); font-variant-numeric: tabular-nums; text-align: right; }
.item.cur .no { color: var(--primary); }
.txt { font-size: 13px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }

@keyframes item-in { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: none; } }
.pop-enter-active { transition: opacity 0.2s, transform 0.26s cubic-bezier(0.34, 1.4, 0.64, 1); }
.pop-leave-active { transition: opacity 0.14s, transform 0.14s; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(-50%) translateX(-10px) scale(0.96); }
.tick-enter-active { transition: opacity 0.3s, transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); }
.tick-enter-from { opacity: 0; transform: scaleX(0); transform-origin: left; }
.nav-enter-active, .nav-leave-active { transition: opacity 0.3s, transform 0.3s var(--ease-out); }
.nav-enter-from, .nav-leave-to { opacity: 0; transform: translateY(-50%) translateX(-8px); }

@media (max-width: 900px) { .mnav { display: none; } }
</style>
