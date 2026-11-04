import { usePreferredDark } from '@vueuse/core'
import { defineStore } from 'pinia'
import { computed, nextTick, ref, watchEffect } from 'vue'

type Mode = 'system' | 'light' | 'dark'

function readMode(): Mode {
  try {
    const v = localStorage.getItem('theme-mode')
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export const useTheme = defineStore('theme', () => {
  const mode = ref<Mode>(readMode())
  const prefersDark = usePreferredDark()
  const isDark = computed(() => (mode.value === 'system' ? prefersDark.value : mode.value === 'dark'))

  watchEffect(() => {
    const root = document.documentElement
    if (mode.value === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', mode.value)
    try {
      localStorage.setItem('theme-mode', mode.value)
    } catch { /* 隐私模式下不可写 */ }
  })

  /**
   * 切换深浅色。支持视图过渡的浏览器：新主题从点击位置以圆形向外展开；
   * 不支持时：给全站加一个短暂的颜色过渡，避免整页"闪"一下。系统开启减少动态效果时直接切换。
   */
  function toggle(e?: MouseEvent) {
    const apply = () => { mode.value = isDark.value ? 'light' : 'dark' }
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const doc = document as Document & { startViewTransition?: (cb: () => Promise<void> | void) => { ready: Promise<void> } }
    if (reduce) return apply()
    if (!doc.startViewTransition) {
      const root = document.documentElement
      root.classList.add('theme-fading')
      apply()
      window.setTimeout(() => root.classList.remove('theme-fading'), 450)
      return
    }
    const x = e?.clientX ?? window.innerWidth / 2
    const y = e?.clientY ?? window.innerHeight / 2
    const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    const t = doc.startViewTransition(async () => { apply(); await nextTick() })
    t.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
        { duration: 520, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', pseudoElement: '::view-transition-new(root)' },
      )
    }).catch(() => { /* 动画失败不影响切换结果 */ })
  }
  return { mode, isDark, toggle }
})
