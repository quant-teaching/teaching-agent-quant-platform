import { usePreferredDark } from '@vueuse/core'
import { defineStore } from 'pinia'
import { computed, ref, watchEffect } from 'vue'

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

  function toggle() {
    mode.value = isDark.value ? 'light' : 'dark'
  }
  return { mode, isDark, toggle }
})
