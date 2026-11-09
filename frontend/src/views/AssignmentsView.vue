<script setup lang="ts">
// 作业：老师给班级布置实验任务，并锁定智能体的工作模式、工具、策略范围与回测上限；
// 学生开始作业后在专属对话里完成，老师可以查看每个人的进度和对话。
import { CalendarClock, ClipboardList, Eye, FlaskConical, Lock, Pencil, Play, Plus, Trash2, Users } from 'lucide-vue-next'
import { NButton, NCheckbox, NDataTable, NDatePicker, NDrawer, NDrawerContent, NEmpty, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, NRadioButton, NRadioGroup, NSelect, NSpin, useMessage, type DataTableColumns } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { accountsApi } from '@/api/accounts'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import { fromServer } from '@/components/chat/convert'
import PageHero from '@/components/common/PageHero.vue'
import { MODES, useAgentControl } from '@/stores/agentControl'
import { useAuth } from '@/stores/auth'
import { useCatalog } from '@/stores/catalog'
import { timeAgo } from '@/utils/format'

const auth = useAuth()
const router = useRouter()
const toast = useMessage()
const catalog = useCatalog()
const ctl = useAgentControl()
const list = ref<any[]>([])
const loading = ref(true)
const teacher = computed(() => auth.isTeacher)

async function load() {
  loading.value = true
  try { list.value = await api.get('/api/assignments') } catch (e: any) { toast.error(e.message) } finally { loading.value = false }
}
onMounted(() => {
  catalog.load().catch(() => {})
  ctl.load()
  if (auth.enabled) load()
  else loading.value = false
})

const modeLabel = (m: string) => MODES.find((x) => x.key === m)?.label ?? m
const stratNames = (ids: string[] | null) => (ids?.length ? ids.map((i) => catalog.byId(i)?.name ?? i).join('、') : '不限')

// ---- 学生
async function start(a: any) {
  try {
    const { session_id } = await api.post<{ session_id: string }>(`/api/assignments/${a.id}/start`)
    router.push(`/chat/${session_id}`)
  } catch (e: any) { toast.error(e.message) }
}

// ---- 老师：布置 / 编辑
const editing = ref<any>(null)
const classes = ref<{ id: number; name: string }[]>([])
async function openEdit(a?: any) {
  if (!classes.value.length) classes.value = (await accountsApi.classes()).map((c) => ({ id: c.id, name: c.name }))
  const c = a?.control ?? {}
  editing.value = {
    id: a?.id ?? null, class_id: a?.class_id ?? classes.value[0]?.id ?? null, title: a?.title ?? '', task: a?.task ?? '', due: a?.due ?? null,
    mode: c.mode ?? 'confirm', tools: c.tools ?? (ctl.meta?.tools.map((t) => t.name) ?? []),
    strategies: c.strategies ?? [], max_backtests: c.max_backtests ?? 12, max_iterations: c.max_iterations ?? 3,
  }
}
const saving = ref(false)
async function save() {
  const e = editing.value
  if (!e.title.trim()) return toast.warning('请填写作业标题')
  if (!e.id && !e.class_id) return toast.warning('请选择班级')
  const body = { title: e.title, task: e.task, due: e.due, control: { mode: e.mode, tools: e.tools, strategies: e.strategies.length ? e.strategies : null, max_backtests: e.max_backtests, max_iterations: e.max_iterations } }
  saving.value = true
  try {
    if (e.id) await api.put(`/api/assignments/${e.id}`, body)
    else await api.post(`/api/classes/${e.class_id}/assignments`, body)
    toast.success(e.id ? '已保存' : '作业已布置')
    editing.value = null
    load()
  } catch (err: any) { toast.error(err.message) } finally { saving.value = false }
}
async function remove(a: any) {
  await api.del(`/api/assignments/${a.id}`)
  toast.success('已删除，学生的对话会保留')
  load()
}
const strategyOptions = computed(() => catalog.strategies.filter((s) => !s.derived).map((s) => ({ label: s.name, value: s.id })))

// ---- 老师：完成情况
const detail = ref<any>(null)
async function openDetail(a: any) {
  detail.value = { ...a, rows: null }
  try { detail.value = await api.get(`/api/assignments/${a.id}`) } catch (e: any) { toast.error(e.message) }
}
const viewing = ref<any>(null)
async function viewSession(row: any) {
  viewing.value = { student: row.display_name, messages: null }
  try {
    const s = await api.get<any>(`/api/assignments/${detail.value.id}/sessions/${row.session_id}`)
    viewing.value = { student: s.student, messages: s.messages.map((m: any) => fromServer(m)) }
  } catch (e: any) { toast.error(e.message); viewing.value = null }
}
const cols: DataTableColumns<any> = [
  { title: '学生', key: 'display_name', render: (r) => h('span', [r.display_name, h('span', { class: 'muted' }, `（${r.username}）`)]) },
  { title: '状态', key: 'status', width: 90, render: (r) => h('span', { class: r.session_id ? 'st on' : 'st' }, r.session_id ? (r.questions ? '进行中' : '已打开') : '未开始') },
  { title: '提问', key: 'questions', width: 70, align: 'right' },
  { title: '回测', key: 'backtests', width: 70, align: 'right' },
  { title: '最近活动', key: 'updated_at', width: 110, render: (r) => (r.updated_at ? timeAgo(r.updated_at) : '—') },
  { title: '', key: 'op', width: 100, render: (r) => r.session_id ? h(NButton, { size: 'tiny', secondary: true, onClick: () => viewSession(r) }, { default: () => '查看对话', icon: () => h(Eye, { size: 13 }) }) : null },
]
</script>

<template>
  <div class="page">
    <PageHero title="作业" tone="amber" :icon="ClipboardList"
      :desc="teacher ? '给班级布置实验任务，并锁定智能体的工作模式、可用工具和策略范围；学生在专属对话里完成，你可以随时查看进度和对话。' : '老师布置的实验任务。开始后会进入一个专属对话，智能体按老师设定的方式协助你完成。'">
      <NButton v-if="teacher && auth.enabled" type="primary" @click="openEdit()"><template #icon><Plus :size="16" /></template>布置作业</NButton>
    </PageHero>

    <div v-if="!auth.enabled" class="card notice">作业功能需要开启登录（多人使用模式），用来区分老师和学生。请在部署时设置 <code>AUTH_ENABLED=1</code>。</div>

    <NSpin v-else :show="loading">
      <NEmpty v-if="!loading && !list.length" :description="teacher ? '还没有布置作业，点右上角「布置作业」' : '老师还没有布置作业'" class="empty" />
      <div class="grid stagger">
        <div v-for="a in list" :key="a.id" class="card item">
          <div class="top">
            <span class="ic-tile tone-amber"><ClipboardList :size="15" /></span>
            <span class="cls">{{ a.class_name }}</span>
            <span v-if="a.due" class="due"><CalendarClock :size="12" /> 截止 {{ a.due }}</span>
          </div>
          <h3>{{ a.title }}</h3>
          <p class="task">{{ a.task || '（没有填写详细要求）' }}</p>
          <div class="locks">
            <span><Lock :size="11" /> {{ modeLabel(a.control.mode) }}</span>
            <span>策略：{{ stratNames(a.control.strategies) }}</span>
            <span>每轮最多回测 {{ a.control.max_backtests }} 次</span>
          </div>
          <div class="foot">
            <template v-if="teacher">
              <span class="prog"><Users :size="13" /> {{ a.started }} / {{ a.students }} 人已开始</span>
              <div class="bar"><i :style="{ width: (a.students ? (a.started / a.students) * 100 : 0) + '%' }" /></div>
              <div class="ops">
                <NButton size="small" secondary @click="openDetail(a)"><template #icon><Eye :size="14" /></template>完成情况</NButton>
                <NButton size="small" quaternary @click="start(a)"><template #icon><FlaskConical :size="14" /></template>试做</NButton>
                <NButton size="small" quaternary @click="openEdit(a)"><template #icon><Pencil :size="14" /></template></NButton>
                <NPopconfirm @positive-click="remove(a)"><template #trigger><NButton size="small" quaternary><template #icon><Trash2 :size="14" /></template></NButton></template>删除这份作业？学生的对话会保留。</NPopconfirm>
              </div>
            </template>
            <template v-else>
              <span class="prog">{{ a.mine ? `已提问 ${a.mine.questions} 次 · 回测 ${a.mine.backtests} 次` : '还没开始' }}</span>
              <NButton type="primary" size="small" @click="start(a)"><template #icon><Play :size="14" /></template>{{ a.mine ? '继续作业' : '开始作业' }}</NButton>
            </template>
          </div>
        </div>
      </div>
    </NSpin>

    <!-- 布置 / 编辑 -->
    <NModal :show="!!editing" preset="card" :title="editing?.id ? '编辑作业' : '布置作业'" style="width: 640px; max-width: calc(100vw - 24px)" @update:show="(v: boolean) => !v && (editing = null)">
      <NForm v-if="editing" label-placement="top" size="small">
        <NFormItem v-if="!editing.id" label="班级"><NSelect v-model:value="editing.class_id" :options="classes.map((c) => ({ label: c.name, value: c.id }))" /></NFormItem>
        <NFormItem label="标题"><NInput v-model:value="editing.title" maxlength="60" placeholder="例如：双均线参数实验" /></NFormItem>
        <NFormItem label="作业要求"><NInput v-model:value="editing.task" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="例如：用双均线策略回测 2022~2025 年，比较两组均线周期，并用稳健性检验判断是否过拟合，最后写出结论" /></NFormItem>
        <NFormItem label="截止日期"><NDatePicker v-model:formatted-value="editing.due" value-format="yyyy-MM-dd" type="date" clearable /></NFormItem>
        <div class="lock-title"><Lock :size="13" /> 锁定智能体（学生在作业对话里无法更改）</div>
        <NFormItem label="工作模式">
          <NRadioGroup v-model:value="editing.mode"><NRadioButton v-for="m in MODES" :key="m.key" :value="m.key">{{ m.label }}</NRadioButton></NRadioGroup>
        </NFormItem>
        <NFormItem label="只允许使用的策略（不选则不限）"><NSelect v-model:value="editing.strategies" multiple filterable :options="strategyOptions" max-tag-count="responsive" /></NFormItem>
        <NFormItem label="允许使用的工具">
          <div class="tools"><NCheckbox v-for="t in ctl.meta?.tools ?? []" :key="t.name" :checked="editing.tools.includes(t.name)"
            @update:checked="(v: boolean) => (editing.tools = v ? [...editing.tools, t.name] : editing.tools.filter((x: string) => x !== t.name))">{{ t.label }}</NCheckbox></div>
        </NFormItem>
        <div class="nums">
          <NFormItem label="每轮最多回测"><NInputNumber v-model:value="editing.max_backtests" :min="1" :max="30" /></NFormItem>
          <NFormItem label="自主研究最多迭代"><NInputNumber v-model:value="editing.max_iterations" :min="1" :max="5" /></NFormItem>
        </div>
      </NForm>
      <template #footer><div class="mfoot"><NButton @click="editing = null">取消</NButton><NButton type="primary" :loading="saving" @click="save">{{ editing?.id ? '保存' : '布置' }}</NButton></div></template>
    </NModal>

    <!-- 完成情况 -->
    <NDrawer :show="!!detail" :width="720" @update:show="(v: boolean) => !v && (detail = null)">
      <NDrawerContent v-if="detail" :title="`完成情况 · ${detail.title}`" closable>
        <p class="muted">{{ detail.class_name }} · 共 {{ detail.rows?.length ?? '…' }} 名学生</p>
        <NSpin :show="!detail.rows"><NDataTable :columns="cols" :data="detail.rows ?? []" size="small" /></NSpin>
      </NDrawerContent>
    </NDrawer>

    <NModal :show="!!viewing" preset="card" :title="`${viewing?.student ?? ''} 的作业对话（只读）`" style="width: 900px; max-width: calc(100vw - 24px)" @update:show="(v: boolean) => !v && (viewing = null)">
      <NSpin :show="!viewing?.messages"><div class="conv">
        <ChatMessage v-for="m in viewing?.messages ?? []" :key="m.key" :msg="m" />
        <NEmpty v-if="viewing?.messages && !viewing.messages.length" description="学生还没有提问" />
      </div></NSpin>
    </NModal>
  </div>
</template>

<style scoped>
.notice { padding: 24px; color: var(--text-2); }
.empty { padding: 60px 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
.item { padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }
.top { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.cls { font-weight: 600; color: var(--t-amber); }
.due { margin-left: auto; display: inline-flex; align-items: center; gap: 3px; color: var(--text-3); }
h3 { margin: 6px 0 0; font-size: 16px; }
.task { margin: 0; font-size: 13px; color: var(--text-2); line-height: 1.6; white-space: pre-wrap; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.locks { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 4px; }
.locks span { display: inline-flex; align-items: center; gap: 3px; font-size: 11.5px; padding: 1px 8px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text-2); }
.foot { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
.prog { display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; color: var(--text-2); flex: 1; }
.bar { width: 100%; height: 5px; border-radius: 999px; background: var(--surface-3); overflow: hidden; order: 3; }
.bar i { display: block; height: 100%; background: var(--t-amber); border-radius: inherit; transition: width 0.6s var(--ease-out); }
.ops { display: flex; gap: 2px; }
.lock-title { display: flex; align-items: center; gap: 5px; font-weight: 650; font-size: 13px; margin: 6px 0 10px; padding-top: 10px; border-top: 1px dashed var(--border); color: var(--t-amber); }
.tools { display: flex; flex-wrap: wrap; gap: 4px 14px; }
.nums { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.mfoot { display: flex; justify-content: flex-end; gap: 8px; }
.conv { max-height: 70vh; overflow-y: auto; padding-right: 6px; }
:deep(.st) { font-size: 12px; color: var(--text-3); }
:deep(.st.on) { color: var(--t-green); font-weight: 600; }
:deep(.muted) { color: var(--text-3); }
</style>
