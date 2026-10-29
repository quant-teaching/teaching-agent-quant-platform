<script setup lang="ts">
import { BookOpen, ChevronsUpDown, FlaskConical, History, KeyRound, Layers, LogOut, MessageSquareText, Moon, Settings2, Sun } from 'lucide-vue-next'
import { NButton, NDropdown, NForm, NFormItem, NInput, NModal, NTooltip, useMessage } from 'naive-ui'
import { computed, h, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/api/client'
import { useAuth } from '@/stores/auth'
import { useTheme } from '@/stores/theme'

const theme = useTheme()
const route = useRoute()
const auth = useAuth()
const message = useMessage()

const me = computed(() => (auth.enabled ? auth.user : null))
const initial = computed(() => (me.value?.display_name || me.value?.username || '?').slice(0, 1).toUpperCase())
const menu = [
  { key: 'password', label: '修改密码', icon: () => h(KeyRound, { size: 15 }) },
  { key: 'logout', label: '退出登录', icon: () => h(LogOut, { size: 15 }) },
]
const pwd = reactive({ show: false, old: '', new: '', confirm: '', saving: false })

function onMenu(key: string) {
  if (key === 'logout') auth.logout()
  else Object.assign(pwd, { show: true, old: '', new: '', confirm: '' })
}

async function changePassword() {
  if (pwd.new !== pwd.confirm) return message.error('两次输入的新密码不一致')
  pwd.saving = true
  try {
    await api.post('/api/auth/password', { old: pwd.old, new: pwd.new })
    message.success('密码已修改')
    pwd.show = false
  } catch (e: any) {
    message.error(e.message)
  } finally {
    pwd.saving = false
  }
}

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

    <NDropdown v-if="me" trigger="click" placement="top-start" :options="menu" @select="onMenu">
      <button class="user" :title="me.display_name">
        <span class="avatar" :class="{ admin: me.role === 'admin' }">{{ initial }}</span>
        <span class="who">
          <b>{{ me.display_name }}</b>
          <em>{{ me.role === 'admin' ? '管理员' : me.username }}</em>
        </span>
        <ChevronsUpDown :size="15" class="chev" />
      </button>
    </NDropdown>

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

  <NModal v-model:show="pwd.show" preset="card" title="修改密码" :bordered="false" style="width: 400px; max-width: calc(100vw - 32px)">
    <NForm label-placement="top" @submit.prevent="changePassword">
      <NFormItem label="原密码"><NInput v-model:value="pwd.old" type="password" show-password-on="click" /></NFormItem>
      <NFormItem label="新密码"><NInput v-model:value="pwd.new" type="password" show-password-on="click" placeholder="8 位以上，包含字母和数字" /></NFormItem>
      <NFormItem label="确认新密码"><NInput v-model:value="pwd.confirm" type="password" show-password-on="click" /></NFormItem>
      <NButton type="primary" block attr-type="submit" :loading="pwd.saving" :disabled="!pwd.old || !pwd.new">保存</NButton>
    </NForm>
  </NModal>
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
.user {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; margin-bottom: 8px;
  border: 1px solid var(--border); border-radius: 11px; background: var(--surface); cursor: pointer;
  font: inherit; text-align: left; color: var(--text-1); transition: background 0.15s;
}
.user:hover { background: var(--surface-3); }
.avatar {
  width: 32px; height: 32px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center;
  font-size: 14px; font-weight: 650; color: var(--primary-ink); background: var(--primary-soft);
}
.avatar.admin { color: #fff; background: var(--primary); }
.who { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.3; }
.who b { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who em { font-style: normal; font-size: 11.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chev { color: var(--text-3); flex-shrink: 0; }
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
  .brand div, .nav-item span, .notice, .who, .chev { display: none; }
  .user { justify-content: center; padding: 6px 0; border: 0; background: none; }
  .brand { justify-content: center; padding-bottom: 14px; }
  .nav-item { justify-content: center; padding: 0; }
  .bottom { flex-direction: column; }
}
</style>
