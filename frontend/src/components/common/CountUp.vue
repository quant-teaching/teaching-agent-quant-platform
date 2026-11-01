<script setup lang="ts">
// 数字滚动：把格式化好的文本（如 "+12.3%"、"1.25"）里的数字从 0 滚到目标值，保留原有的符号、小数位和单位
import { onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ value: string; duration?: number }>(), { duration: 900 })
const shown = ref(props.value)
let raf = 0

function run(text: string) {
  cancelAnimationFrame(raf)
  const m = text.match(/-?\d[\d,]*(\.\d+)?/)
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (!m || reduce) return void (shown.value = text)
  const target = Number(m[0].replace(/,/g, ''))
  const decimals = m[1] ? m[1].length - 1 : 0
  const [head, tail] = [text.slice(0, m.index), text.slice(m.index! + m[0].length)]
  const t0 = performance.now()
  const step = (now: number) => {
    const p = Math.min(1, (now - t0) / props.duration)
    const eased = 1 - Math.pow(1 - p, 3)
    shown.value = head + (target * eased).toFixed(decimals) + tail
    if (p < 1) raf = requestAnimationFrame(step)
    else shown.value = text
  }
  raf = requestAnimationFrame(step)
}

watch(() => props.value, run, { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <span>{{ shown }}</span>
</template>
