<script setup lang="ts">
// 用户管理（管理员）：全部账号的增删改查，可按角色、班级筛选，可修改角色和所属班级
import { Ban, CircleCheck, KeyRound, MoreHorizontal, Pencil, Search, Trash2, UserPlus, Users } from 'lucide-vue-next'
import { NButton, NDataTable, NDropdown, NForm, NFormItem, NInput, NModal, NRadioButton, NRadioGroup, NSelect, NTag, useDialog, useMessage, type DataTableColumns } from 'naive-ui'
import { computed, h, onMounted, reactive, ref } from 'vue'
import { accountsApi, ROLE_TEXT, type ClassInfo, type ManagedUser, type Role } from '@/api/accounts'
import { useAuth } from '@/stores/auth'
import { timeAgo } from '@/utils/format'
import PasswordReveal from './PasswordReveal.vue'

const auth = useAuth()
const toast = useMessage()
const dialog = useDialog()
const users = ref<ManagedUser[]>([])
const classes = ref<ClassInfo[]>([])
const loading = ref(true)
const role = ref<'all' | Role>('all')
const classFilter = ref<number | null>(null)
const q = ref('')

async function load() {
  loading.value = true
  try {
    ;[users.value, classes.value] = await Promise.all([accountsApi.users(), accountsApi.classes()])
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const counts = computed(() => ({
  all: users.value.length,
  admin: users.value.filter((u) => u.role === 'admin').length,
  teacher: users.value.filter((u) => u.role === 'teacher').length,
  student: users.value.filter((u) => u.role === 'student').length,
}))
const list = computed(() => {
  const k = q.value.trim().toLowerCase()
  return users.value.filter((u) => (role.value === 'all' || u.role === role.value)
    && (classFilter.value === null || u.class_id === classFilter.value)
    && (!k || u.username.toLowerCase().includes(k) || u.display_name.toLowerCase().includes(k)))
})
const classOptions = computed(() => classes.value.map((c) => ({ label: `${c.name}${c.teacher_name ? `（${c.teacher_name}）` : ''}`, value: c.id })))
const roleOptions = (Object.keys(ROLE_TEXT) as Role[]).map((r) => ({ label: ROLE_TEXT[r], value: r }))

// 新建 / 编辑
const form = reactive({ show: false, id: null as number | null, username: '', display_name: '', password: '', role: 'student' as Role,
  class_id: null as number | null, saving: false })
const reveal = reactive({ show: false, username: '', password: '', title: '' })
function openForm(u?: ManagedUser) {
  Object.assign(form, { show: true, id: u?.id ?? null, username: u?.username ?? '', display_name: u?.display_name ?? '', password: '',
    role: u?.role ?? 'student', class_id: u?.class_id ?? classes.value[0]?.id ?? null })
}
async function saveForm() {
  form.saving = true
  try {
    const class_id = form.role === 'student' ? form.class_id : null
    if (form.id) {
      await accountsApi.updateUser(form.id, { display_name: form.display_name, role: form.role, class_id })
      toast.success('已保存')
    } else {
      const u = await accountsApi.createUser({ username: form.username.trim(), display_name: form.display_name.trim(), password: form.password, role: form.role, class_id })
      Object.assign(reveal, { show: true, username: u.username, password: u.initial_password!, title: `${u.role_label}账号已创建` })
    }
    form.show = false
    load()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    form.saving = false
  }
}

function reset(u: ManagedUser) {
  dialog.warning({
    title: '重置密码', content: `为 ${u.display_name}（${u.username}）生成新的随机密码？对方当前的登录会失效。`, positiveText: '重置', negativeText: '取消',
    onPositiveClick: async () => {
      const r = await accountsApi.resetPassword(u.id)
      Object.assign(reveal, { show: true, username: u.username, password: r.password, title: '密码已重置' })
    },
  })
}
async function toggle(u: ManagedUser) {
  try { Object.assign(u, await accountsApi.updateUser(u.id, { disabled: !u.disabled })); toast.success(u.disabled ? '已停用' : '已启用') } catch (e: any) { toast.error(e.message) }
}
function remove(u: ManagedUser) {
  dialog.error({
    title: '删除账号', content: `确定删除 ${u.display_name}（${u.username}）吗？此操作无法恢复。`, positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      try { await accountsApi.deleteUser(u.id); toast.success('已删除'); load() } catch (e: any) { toast.error(e.message) }
    },
  })
}
const isMe = (u: ManagedUser) => u.id === auth.user?.id
const rowMenu = (u: ManagedUser) => [
  { key: 'edit', label: '编辑', icon: () => h(Pencil, { size: 14 }) },
  { key: 'reset', label: '重置密码', icon: () => h(KeyRound, { size: 14 }), disabled: u.role === 'admin' && !isMe(u) },
  { key: 'toggle', label: u.disabled ? '启用账号' : '停用账号', icon: () => h(u.disabled ? CircleCheck : Ban, { size: 14 }), disabled: isMe(u) },
  { type: 'divider', key: 'd' },
  { key: 'delete', label: '删除账号', icon: () => h(Trash2, { size: 14 }), disabled: isMe(u) },
]
function onRow(k: string, u: ManagedUser) {
  if (k === 'edit') openForm(u)
  else if (k === 'reset') reset(u)
  else if (k === 'toggle') toggle(u)
  else if (k === 'delete') remove(u)
}
const TAG: Record<Role, 'error' | 'info' | 'default'> = { admin: 'error', teacher: 'info', student: 'default' }
const cols: DataTableColumns<ManagedUser> = [
  { title: '用户', key: 'display_name', minWidth: 170,
    render: (u) => h('div', { class: 'who' }, [h('span', { class: ['av', u.role] }, (u.display_name || u.username).slice(0, 1)),
      h('div', [h('b', [u.display_name || u.username, isMe(u) ? h('i', { class: 'me' }, '（我）') : null]), h('em', u.username)])]) },
  { title: '角色', key: 'role', width: 86, render: (u) => h(NTag, { size: 'small', round: true, bordered: false, type: TAG[u.role] }, () => u.role_label) },
  { title: '班级', key: 'class_name', minWidth: 120, render: (u) => h('span', { class: u.class_name ? '' : 'muted' }, u.class_name ?? '—') },
  { title: '状态', key: 'disabled', width: 80, render: (u) => h('span', { class: u.disabled ? 'muted' : 'ok' }, u.disabled ? '已停用' : '正常') },
  { title: '回测', key: 'backtest_count', width: 70, align: 'right', sorter: (a, b) => a.backtest_count - b.backtest_count },
  { title: '最近登录', key: 'last_login', width: 110, render: (u) => h('span', { class: 'muted' }, u.last_login ? timeAgo(u.last_login) : '从未登录') },
  { title: '注册时间', key: 'created_at', width: 110, render: (u) => h('span', { class: 'muted' }, u.created_at.slice(0, 10)) },
  { title: '', key: 'ops', width: 56, align: 'center',
    render: (u) => h(NDropdown, { trigger: 'click', options: rowMenu(u), onSelect: (k: string) => onRow(k, u) },
      () => h(NButton, { size: 'small', quaternary: true, circle: true }, { icon: () => h(MoreHorizontal, { size: 16 }) })) },
]
</script>

<template>
  <div class="panel-body">
    <section class="card card-pad">
      <div class="head">
        <div>
          <h3 class="section-title"><Users :size="16" class="ti" /> 全部账号</h3>
          <p class="section-sub">管理员可以创建任意角色的账号、修改角色和所属班级。老师只能在「班级管理」里管理自己班级的学生。</p>
        </div>
        <NButton type="primary" @click="openForm()"><template #icon><UserPlus :size="16" /></template>新建账号</NButton>
      </div>
      <div class="tb">
        <NRadioGroup v-model:value="role" size="small">
          <NRadioButton value="all">全部 {{ counts.all }}</NRadioButton>
          <NRadioButton value="admin">管理员 {{ counts.admin }}</NRadioButton>
          <NRadioButton value="teacher">老师 {{ counts.teacher }}</NRadioButton>
          <NRadioButton value="student">学生 {{ counts.student }}</NRadioButton>
        </NRadioGroup>
        <NSelect v-model:value="classFilter" :options="classOptions" clearable placeholder="按班级筛选" size="small" class="cf" />
        <NInput v-model:value="q" size="small" clearable placeholder="搜索姓名或用户名" class="search"><template #prefix><Search :size="14" /></template></NInput>
      </div>
      <NDataTable :columns="cols" :data="list" :loading="loading" size="small" :bordered="false" :pagination="{ pageSize: 20 }" :scroll-x="860" />
    </section>

    <NModal v-model:show="form.show" preset="card" :title="form.id ? '编辑账号' : '新建账号'" :bordered="false" style="width: 440px; max-width: calc(100vw - 32px)">
      <NForm label-placement="top" @submit.prevent="saveForm">
        <NFormItem v-if="!form.id" label="用户名（登录用）"><NInput v-model:value="form.username" :maxlength="20" placeholder="2~20 位中文、字母、数字或下划线" /></NFormItem>
        <NFormItem label="显示名称"><NInput v-model:value="form.display_name" :maxlength="20" placeholder="例如：王老师、张三" /></NFormItem>
        <NFormItem label="角色"><NSelect v-model:value="form.role" :options="roleOptions" :disabled="!!form.id && form.id === auth.user?.id" /></NFormItem>
        <NFormItem v-if="form.role === 'student'" label="所属班级"><NSelect v-model:value="form.class_id" :options="classOptions" placeholder="学生必须属于一个班级" /></NFormItem>
        <NFormItem v-if="!form.id" label="初始密码（选填）"><NInput v-model:value="form.password" :maxlength="64" placeholder="留空则自动生成 8 位随机密码" /></NFormItem>
        <NButton type="primary" block attr-type="submit" :loading="form.saving">{{ form.id ? '保存' : '创建账号' }}</NButton>
      </NForm>
    </NModal>
    <PasswordReveal v-model:show="reveal.show" :username="reveal.username" :password="reveal.password" :title="reveal.title" />
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.ti { vertical-align: -2px; margin-right: 2px; }
.tb { display: flex; align-items: center; gap: 10px; margin: 6px 0 12px; flex-wrap: wrap; }
.cf { width: 200px; }
.search { width: 200px; }
:deep(.who) { display: flex; align-items: center; gap: 10px; }
:deep(.who .av) { width: 30px; height: 30px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center; font-weight: 650; font-size: 13px; color: var(--primary-ink); background: var(--primary-soft); }
:deep(.who .av.admin) { color: #fff; background: var(--brand-grad); }
:deep(.who .av.teacher) { color: var(--t-teal); background: var(--t-teal-soft); }
:deep(.who b) { display: block; font-size: 13.5px; font-weight: 600; }
:deep(.who em) { display: block; font-style: normal; font-size: 11.5px; color: var(--text-3); }
:deep(.me) { font-style: normal; font-weight: 400; color: var(--text-3); }
:deep(.ok) { color: var(--c-tip); }
@media (max-width: 700px) { .head { flex-direction: column; } }
</style>
