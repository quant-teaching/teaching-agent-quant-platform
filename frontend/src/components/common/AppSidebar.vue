<script setup lang="ts">
import { BookOpen, FlaskConical, History, Layers, MessageSquareText, Moon, Settings2, Sun } from 'lucide-vue-next'
import { NTooltip } from 'naive-ui'
import { useRoute } from 'vue-router'
import { useTheme } from '@/stores/theme'

const theme = useTheme()
const route = useRoute()

const items = [
  { to: '/chat', name: 'chat', label: '智能助手', icon: MessageSquareText },
  { to: '/library', name: 'library', label: '算法库', icon: BookOpen, also: ['strategy'] },
  { to: '/backtest', name: 'backtest', label: '回测实验室', icon: FlaskConical },
  { to: '/portfolio', name: 'portfolio', label: '组合实验室', icon: Layers },
  { to: '/history', name: 'history', label: '回测记录', icon: History, also: ['report'] },
]

function active(it: (typeof items)[number]) {
  return route.name === it.name || (it.also ?? []).includes(route.name as string)
}
</script>

<template>
  <aside class="sidebar">
    <RouterLink to="/chat" class="brand">
      <img src="/logo.svg" alt="" width="30" height="30" />
      <div>
        <div class="brand-name">量化策略教学平台</div>
        <div class="brand-sub">智能体驱动 · 教学实验</div>
      </div>
    </RouterLink>

    <nav class="nav">
      <RouterLink v-for="it in items" :key="it.to" :to="it.to" class="nav-item" :class="{ active: active(it) }">
        <component :is="it.icon" :size="18" :stroke-width="1.8" />
        <span>{{ it.label }}</span>
      </RouterLink>
    </nav>

    <div class="spacer" />

    <div class="notice">
      本平台为教学实验工具，回测结果仅用于算法学习与教学演示，不构成任何投资建议。
    </div>

    <div class="bottom">
      <RouterLink to="/settings" class="nav-item" :class="{ active: route.name === 'settings' }">
        <Settings2 :size="18" :stroke-width="1.8" />
        <span>模型设置</span>
      </RouterLink>
      <NTooltip placement="right">
        <template #trigger>
          <button class="icon-btn" :aria-label="theme.isDark ? '切换到浅色' : '切换到深色'" @click="theme.toggle()">
            <Sun v-if="theme.isDark" :size="17" />
            <Moon v-else :size="17" />
          </button>
        </template>
        {{ theme.isDark ? '切换到浅色模式' : '切换到深色模式' }}
      </NTooltip>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 18px 14px 14px;
  background: var(--surface);
  border-right: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 10px; padding: 2px 6px 18px; color: var(--text-1); }
.brand-name { font-size: 14.5px; font-weight: 650; letter-spacing: 0.3px; }
.brand-sub { font-size: 11.5px; color: var(--text-3); }
.nav { display: flex; flex-direction: column; gap: 2px; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  height: 38px; padding: 0 12px; border-radius: 9px;
  color: var(--text-2); font-size: 14px; transition: background 0.15s, color 0.15s;
}
.nav-item:hover { background: var(--surface-3); color: var(--text-1); }
.nav-item.active { background: var(--primary-soft); color: var(--primary-ink); font-weight: 600; }
.spacer { flex: 1; }
.notice {
  font-size: 11.5px; line-height: 1.6; color: var(--text-3);
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; margin-bottom: 10px;
}
.bottom { display: flex; align-items: center; gap: 6px; }
.bottom .nav-item { flex: 1; }
.icon-btn {
  width: 38px; height: 38px; border-radius: 9px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-2); cursor: pointer;
  display: grid; place-items: center; transition: background 0.15s;
}
.icon-btn:hover { background: var(--surface-3); color: var(--text-1); }
@media (max-width: 900px) {
  .sidebar { width: 64px; padding: 14px 10px; }
  .brand div, .nav-item span, .notice { display: none; }
  .brand { justify-content: center; padding-bottom: 14px; }
  .nav-item { justify-content: center; padding: 0; }
  .bottom { flex-direction: column; }
}
</style>
