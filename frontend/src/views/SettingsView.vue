<script setup lang="ts">
// 设置：按角色显示不同的分区。学生：个人账号、模型接口（只读）；老师：再加班级管理；管理员：再加用户管理和注册设置
import { Cpu, Presentation, School, Server, Settings2, UserRound, Users } from 'lucide-vue-next'
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHero from '@/components/common/PageHero.vue'
import AccountPanel from '@/components/settings/AccountPanel.vue'
import ClassPanel from '@/components/settings/ClassPanel.vue'
import ModelPanel from '@/components/settings/ModelPanel.vue'
import MyModelsPanel from '@/components/settings/MyModelsPanel.vue'
import RegisterPanel from '@/components/settings/RegisterPanel.vue'
import UserPanel from '@/components/settings/UserPanel.vue'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()

interface Tab { key: string; label: string; desc: string; icon: any; tone: string; comp: any }
const tabs = computed<Tab[]>(() => {
  const role = auth.user?.role
  const out: Tab[] = []
  if (auth.enabled) out.push({ key: 'account', label: '个人账号', desc: '显示名称与密码', icon: UserRound, tone: 'blue', comp: AccountPanel })
  if (role === 'admin' || role === 'teacher')
    out.push({ key: 'classes', label: '班级管理', desc: role === 'admin' ? '全部班级与学生' : '我的班级与学生', icon: School, tone: 'violet', comp: ClassPanel })
  if (role === 'admin') {
    out.push({ key: 'users', label: '用户管理', desc: '全部账号增删改查', icon: Users, tone: 'rose', comp: UserPanel })
    out.push({ key: 'register', label: '注册设置', desc: '教师注册码', icon: Presentation, tone: 'amber', comp: RegisterPanel })
  }
  if (auth.enabled && role !== 'admin')
    out.push({ key: 'mine', label: '我的模型', desc: '添加自己的模型渠道', icon: Server, tone: 'green', comp: MyModelsPanel })
  out.push({ key: 'model', label: role === 'admin' || !auth.enabled ? '模型接口' : '平台模型', desc: role === 'admin' || !auth.enabled ? '接口与主备顺序' : '查看当前使用的模型', icon: Cpu, tone: 'teal', comp: ModelPanel })
  return out
})
const defaultTab = computed(() => (auth.user?.role === 'teacher' || auth.user?.role === 'admin' ? 'classes' : tabs.value[0].key))
const active = computed(() => tabs.value.find((t) => t.key === route.query.tab) ?? tabs.value.find((t) => t.key === defaultTab.value)!)
function go(key: string) { router.replace({ query: { ...route.query, tab: key } }) }
watch(() => route.query.tab, (v) => { if (v && !tabs.value.some((t) => t.key === v)) go(defaultTab.value) })
</script>

<template>
  <div class="page settings">
    <PageHero title="设置" tone="teal" :icon="Settings2"
      :desc="auth.user?.role === 'student' ? '管理你的个人账号，查看平台当前使用的模型。' : '管理个人账号、班级与学生、注册方式和大模型接口。不同角色看到的分区不同。'" />

    <div class="layout">
      <nav class="tabs" aria-label="设置分区">
        <button v-for="t in tabs" :key="t.key" class="tab" :class="[`tone-${t.tone}`, { on: t.key === active.key }]" @click="go(t.key)">
          <span class="ic-tile"><component :is="t.icon" :size="16" /></span>
          <span class="tt"><b>{{ t.label }}</b><em>{{ t.desc }}</em></span>
        </button>
      </nav>
      <main class="content">
        <Transition name="learn-swap" mode="out-in">
          <component :is="active.comp" :key="active.key" />
        </Transition>
      </main>
    </div>
  </div>
</template>

<style scoped>
.settings { max-width: 1280px; }
.layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 18px; align-items: start; }
.tabs { position: sticky; top: 20px; display: flex; flex-direction: column; gap: 6px; }
.tab {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; cursor: pointer; text-align: left;
  border: 1px solid transparent; background: none; font: inherit; color: var(--text-2); transition: background 0.15s, border-color 0.2s;
}
.tab:hover { background: var(--surface-3); }
.tab.on { background: var(--surface); border-color: color-mix(in srgb, var(--tone) 35%, var(--border)); box-shadow: var(--shadow-sm); }
.tab.on .ic-tile { color: #fff; background: var(--tone); }
.tt { display: flex; flex-direction: column; min-width: 0; }
.tt b { font-size: 14px; color: var(--text-1); font-weight: 600; }
.tt em { font-style: normal; font-size: 11.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.content { min-width: 0; }
.content :deep(.panel-body) { display: flex; flex-direction: column; gap: 14px; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .tabs { position: static; flex-direction: row; overflow-x: auto; }
  .tab { flex-shrink: 0; }
  .tt em { display: none; }
}
</style>
