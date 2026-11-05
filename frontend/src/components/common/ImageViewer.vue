<script setup lang="ts">
// 图片查看器：滚轮以鼠标位置为中心缩放、拖动平移、双击复位，Esc 关闭，+ / − / 0 快捷键
import { Maximize2, Minus, Plus, X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { viewer } from '@/stores/viewer'

const MIN = 0.2
const MAX = 8
const st = reactive({ scale: 1, x: 0, y: 0, dragging: false, fit: 1 })
const img = ref<HTMLImageElement | null>(null)
let start = { x: 0, y: 0, ox: 0, oy: 0 }

const style = computed(() => ({ transform: `translate(${st.x}px, ${st.y}px) scale(${st.scale})` }))
const percent = computed(() => Math.round((st.scale / st.fit) * 100))

function reset() {
  Object.assign(st, { scale: st.fit, x: 0, y: 0 })
}
function onLoad() {
  const el = img.value
  if (!el) return
  // 初始按"完整放进窗口"显示，最大不超过原图大小
  st.fit = Math.min(1, (window.innerWidth * 0.9) / el.naturalWidth, (window.innerHeight * 0.82) / el.naturalHeight)
  reset()
}
function zoomAt(factor: number, cx = window.innerWidth / 2, cy = window.innerHeight / 2) {
  const next = Math.min(MAX, Math.max(MIN, st.scale * factor))
  const k = next / st.scale
  // 以 (cx, cy) 为中心缩放：保持鼠标下方的像素不动
  const ox = cx - window.innerWidth / 2
  const oy = cy - window.innerHeight / 2
  st.x = ox - (ox - st.x) * k
  st.y = oy - (oy - st.y) * k
  st.scale = next
}
function onWheel(e: WheelEvent) {
  zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY)
}
function onDown(e: PointerEvent) {
  if (e.button !== 0) return
  st.dragging = true
  start = { x: e.clientX, y: e.clientY, ox: st.x, oy: st.y }
  ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
}
function onMove(e: PointerEvent) {
  if (!st.dragging) return
  st.x = start.ox + e.clientX - start.x
  st.y = start.oy + e.clientY - start.y
}
function onUp() { st.dragging = false }
function close() { viewer.open = false }
function onKey(e: KeyboardEvent) {
  if (!viewer.open) return
  if (e.key === 'Escape') close()
  else if (e.key === '+' || e.key === '=') zoomAt(1.25)
  else if (e.key === '-') zoomAt(0.8)
  else if (e.key === '0') reset()
  else return
  e.preventDefault()
  e.stopPropagation() // Esc 只关闭图片，不连带退出全屏阅读
}
watch(() => viewer.open, async (v) => {
  if (v) {
    window.addEventListener('keydown', onKey, true)
    await nextTick()
    if (img.value?.complete) onLoad()
  } else window.removeEventListener('keydown', onKey, true)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <Teleport to="body">
    <Transition name="iv">
      <div v-if="viewer.open" class="iv" @wheel.prevent="onWheel" @click.self="close">
        <img ref="img" :src="viewer.src" :alt="viewer.alt" class="iv-img" :class="{ dragging: st.dragging }" :style="style"
          draggable="false" @load="onLoad" @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp"
          @dblclick="reset" />
        <div class="iv-bar" @click.stop>
          <button title="缩小（-）" @click="zoomAt(0.8)"><Minus :size="17" /></button>
          <span class="iv-pct">{{ percent }}%</span>
          <button title="放大（+）" @click="zoomAt(1.25)"><Plus :size="17" /></button>
          <span class="iv-sep" />
          <button title="适应窗口（0 或双击图片）" @click="reset"><Maximize2 :size="16" /></button>
          <button title="关闭（Esc）" @click="close"><X :size="18" /></button>
        </div>
        <div v-if="viewer.alt" class="iv-cap">{{ viewer.alt }}</div>
        <div class="iv-tip">滚轮缩放 · 拖动平移 · 双击复位 · Esc 关闭</div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.iv {
  position: fixed; inset: 0; z-index: 3000; overflow: hidden; display: grid; place-items: center;
  background: rgba(8, 12, 20, 0.86); backdrop-filter: blur(4px); cursor: zoom-out;
}
.iv-img {
  max-width: none; max-height: none; border-radius: 10px; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
  cursor: grab; user-select: none; touch-action: none; transform-origin: center center;
  transition: transform 0.12s ease-out;
}
.iv-img.dragging { cursor: grabbing; transition: none; }
.iv-bar {
  position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%); display: flex; align-items: center; gap: 4px;
  padding: 6px 8px; border-radius: 999px; background: rgba(30, 34, 42, 0.88); border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35); cursor: default;
}
.iv-bar button {
  width: 34px; height: 34px; border: 0; border-radius: 50%; display: grid; place-items: center; cursor: pointer;
  color: #e8ecf2; background: transparent; transition: background 0.15s;
}
.iv-bar button:hover { background: rgba(255, 255, 255, 0.14); }
.iv-pct { min-width: 52px; text-align: center; font-size: 13px; color: #e8ecf2; font-variant-numeric: tabular-nums; }
.iv-sep { width: 1px; height: 18px; margin: 0 4px; background: rgba(255, 255, 255, 0.18); }
.iv-cap { position: absolute; top: 22px; left: 50%; transform: translateX(-50%); max-width: 80vw; padding: 6px 14px; border-radius: 999px;
  font-size: 13px; color: #e8ecf2; background: rgba(30, 34, 42, 0.75); pointer-events: none; }
.iv-tip { position: absolute; right: 20px; bottom: 36px; font-size: 12px; color: rgba(232, 236, 242, 0.55); pointer-events: none; }
.iv-enter-active, .iv-leave-active { transition: opacity 0.22s ease; }
.iv-enter-active .iv-img { animation: pop 0.28s var(--ease-out) both; }
.iv-enter-from, .iv-leave-to { opacity: 0; }
@media (max-width: 640px) { .iv-tip { display: none; } }
</style>
