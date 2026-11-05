<script setup lang="ts">
import { darkTheme, dateZhCN, NConfigProvider, NDialogProvider, NMessageProvider, zhCN, type GlobalThemeOverrides } from 'naive-ui'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/common/AppSidebar.vue'
import ImageViewer from '@/components/common/ImageViewer.vue'
import { useTheme } from '@/stores/theme'

const theme = useTheme()
const route = useRoute()

const overrides = computed<GlobalThemeOverrides>(() => {
  const dark = theme.isDark
  const primary = dark ? '#3987e5' : '#2a78d6'
  return {
    common: {
      primaryColor: primary,
      primaryColorHover: dark ? '#5598e7' : '#3987e5',
      primaryColorPressed: dark ? '#2a78d6' : '#256abf',
      primaryColorSuppl: primary,
      borderRadius: '8px',
      borderRadiusSmall: '6px',
      fontFamily: 'var(--font)',
      fontSize: '14px',
      bodyColor: dark ? '#111213' : '#f4f5f7',
      cardColor: dark ? '#1a1a19' : '#ffffff',
      modalColor: dark ? '#1a1a19' : '#ffffff',
      popoverColor: dark ? '#202120' : '#ffffff',
      tableColor: dark ? '#1a1a19' : '#ffffff',
      borderColor: dark ? '#2e2f2d' : '#e5e7eb',
      dividerColor: dark ? '#2e2f2d' : '#eceef1',
      errorColor: dark ? '#f07070' : '#d93a3a',
      successColor: dark ? '#3cc48f' : '#12875c',
    },
    Card: { borderRadius: '12px', paddingMedium: '18px 20px' },
    Button: { fontWeight: '500' },
    DataTable: { thColor: dark ? '#202120' : '#f7f8fa', tdColorHover: dark ? '#232423' : '#f7f8fa' },
    Tag: { borderRadius: '6px' },
  }
})
</script>

<template>
  <NConfigProvider :theme="theme.isDark ? darkTheme : null" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider placement="top">
      <NDialogProvider>
        <ImageViewer />
        <RouterView v-if="route.meta.bare" />
        <div v-else class="shell">
          <AppSidebar />
          <main class="main" :class="{ full: route.meta.full }">
            <RouterView v-slot="{ Component }">
              <transition name="fade" mode="out-in">
                <component :is="Component" :key="route.name === 'chat' || route.name === 'learn' ? String(route.name) : route.fullPath" />
              </transition>
            </RouterView>
          </main>
        </div>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.shell { display: flex; height: 100vh; }
.main { flex: 1; min-width: 0; height: 100%; overflow-y: auto; }
.main.full { overflow: hidden; }
.fade-enter-active { transition: opacity 0.28s var(--ease-out), transform 0.28s var(--ease-out); }
.fade-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.fade-enter-from { opacity: 0; transform: translateY(8px); }
.fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
