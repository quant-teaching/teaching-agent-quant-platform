<script setup lang="ts">
// 班级详情：近 30 天活跃度图表 + 学生列表（新建、编辑、重置密码、停用、移班、删除、查看回测）+ 批量导入
import { ArrowLeft, Copy, Download, FileUp, KeyRound, MoreHorizontal, Pencil, Search, Trash2, UserPlus, ArrowRightLeft, Ban, CircleCheck, LineChart, Gauge } from 'lucide-vue-next'
import { NButton, NDataTable, NDrawer, NDrawerContent, NDropdown, NEmpty, NForm, NFormItem, NInput, NModal, NSelect, NSwitch, NTag, NTooltip, useDialog, useMessage, type DataTableColumns } from 'naive-ui'
import VChart from 'vue-echarts'
import { computed, h, onMounted, reactive, ref } from 'vue'
import { accountsApi, copyText, downloadCsv, quotaText, type ClassInfo, type ManagedUser } from '@/api/accounts'
import { axisStyle, baseOption, useChartTokens } from '@/charts/theme'
import { pct, timeAgo } from '@/utils/format'
import ImportModal from './ImportModal.vue'
import OnceCodes from './OnceCodes.vue'
import QuotaModal from './QuotaModal.vue'
import PasswordReveal from './PasswordReveal.vue'

const props = defineProps<{ room: ClassInfo; classes: ClassInfo[] }>()
const emit = defineEmits<{ back: []; changed: [] }>()
const toast = useMessage()
const dialog = useDialog()
const tk = useChartTokens()

const students = ref<ManagedUser[]>([])
const activity = ref<{ dates: string[]; backtests: number[]; active: number[] } | null>(null)
const loading = ref(true)
const q = ref('')

async function load() {
  loading.value = true
  try {
    const [u, a] = await Promise.all([accountsApi.users({ class_id: props.room.id, role: 'student' }), accountsApi.activity(props.room.id)])
    students.value = u
    activity.value = a
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)
function changed() { load(); emit('changed') }

const list = computed(() => {
  const k = q.value.trim().toLowerCase()
  return k ? students.value.filter((u) => u.username.toLowerCase().includes(k) || u.display_name.toLowerCase().includes(k)) : students.value
})

// 近 30 天每日回测次数（单一序列；活跃人数放在提示框里，避免双坐标轴）
const chart = computed(() => {
  const a = activity.value
  const t = tk.value
  if (!a) return {}
  return {
    ...baseOption(t),
    grid: { left: 4, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.grid, opacity: 0.6 } },
      formatter: (ps: any[]) => { const i = ps[0].dataIndex; return `${a.dates[i]}<br/>回测 <b>${a.backtests[i]}</b> 次 · 活跃 <b>${a.active[i]}</b> 人` },
    },
    xAxis: { type: 'category', data: a.dates.map((d) => d.slice(5)), ...axisStyle(t), axisLabel: { color: t.text3, fontSize: 10, interval: 4 } },
    yAxis: { type: 'value', minInterval: 1, ...axisStyle(t), axisLabel: { color: t.text3, fontSize: 10 } },
    series: [{ type: 'bar', data: a.backtests, barMaxWidth: 14, itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] } }],
  }
})
const monthTotal = computed(() => activity.value?.backtests.reduce((s, v) => s + v, 0) ?? 0)
const neverLogin = computed(() => students.value.filter((u) => !u.last_login).length)

// ---------------- 新建 / 编辑
const form = reactive({ show: false, id: null as number | null, username: '', display_name: '', password: '', saving: false })
const reveal = reactive({ show: false, username: '', password: '', title: '' })
function openForm(u?: ManagedUser) {
  Object.assign(form, { show: true, id: u?.id ?? null, username: u?.username ?? '', display_name: u?.display_name ?? '', password: '' })
}
async function saveForm() {
  form.saving = true
  try {
    if (form.id) {
      await accountsApi.updateUser(form.id, { display_name: form.display_name })
      toast.success('已保存')
    } else {
      const u = await accountsApi.createUser({ username: form.username.trim(), display_name: form.display_name.trim(), password: form.password, class_id: props.room.id })
      Object.assign(reveal, { show: true, username: u.username, password: u.initial_password!, title: '学生账号已创建' })
    }
    form.show = false
    changed()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    form.saving = false
  }
}

// ---------------- 行操作
const move = reactive({ show: false, user: null as ManagedUser | null, target: null as number | null })
const others = computed(() => props.classes.filter((c) => c.id !== props.room.id).map((c) => ({ label: c.name, value: c.id })))
async function doMove() {
  if (!move.user || !move.target) return
  try {
    await accountsApi.updateUser(move.user.id, { class_id: move.target })
    toast.success(`已把 ${move.user.display_name} 移到「${props.classes.find((c) => c.id === move.target)?.name}」`)
    move.show = false
    changed()
  } catch (e: any) { toast.error(e.message) }
}
function reset(u: ManagedUser) {
  dialog.warning({
    title: '重置密码', content: `为 ${u.display_name}（${u.username}）生成一个新的随机密码？对方当前的登录会失效。`, positiveText: '重置', negativeText: '取消',
    onPositiveClick: async () => {
      const r = await accountsApi.resetPassword(u.id)
      Object.assign(reveal, { show: true, username: u.username, password: r.password, title: '密码已重置' })
    },
  })
}
async function toggleDisabled(u: ManagedUser) {
  try {
    Object.assign(u, await accountsApi.updateUser(u.id, { disabled: !u.disabled }))
    toast.success(u.disabled ? '已停用，对方已被退出登录' : '已启用')
    emit('changed')
  } catch (e: any) { toast.error(e.message) }
}
function remove(u: ManagedUser) {
  dialog.error({
    title: '删除学生', content: `确定删除 ${u.display_name}（${u.username}）吗？账号删除后无法恢复，他的回测记录会保留但无法再登录查看。`,
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => { await accountsApi.deleteUser(u.id); toast.success('已删除'); changed() },
  })
}
const rowMenu = (u: ManagedUser) => [
  { key: 'edit', label: '修改姓名', icon: () => h(Pencil, { size: 14 }) },
  { key: 'reset', label: '重置密码', icon: () => h(KeyRound, { size: 14 }) },
  { key: 'move', label: '移到其他班级', icon: () => h(ArrowRightLeft, { size: 14 }), disabled: !others.value.length },
  { key: 'records', label: '查看回测记录', icon: () => h(LineChart, { size: 14 }) },
  { key: 'quota', label: '设置每日次数', icon: () => h(Gauge, { size: 14 }) },
  { key: 'toggle', label: u.disabled ? '启用账号' : '停用账号', icon: () => h(u.disabled ? CircleCheck : Ban, { size: 14 }) },
  { type: 'divider', key: 'd' },
  { key: 'delete', label: '删除账号', icon: () => h(Trash2, { size: 14 }) },
]
function onRow(key: string, u: ManagedUser) {
  if (key === 'edit') openForm(u)
  else if (key === 'reset') reset(u)
  else if (key === 'move') Object.assign(move, { show: true, user: u, target: null })
  else if (key === 'records') openRecords(u)
  else if (key === 'quota') editUserQuota(u)
  else if (key === 'toggle') toggleDisabled(u)
  else if (key === 'delete') remove(u)
}

// ---------------- 学生的回测记录（只读）
const rec = reactive({ show: false, user: null as ManagedUser | null, rows: [] as any[], loading: false })
async function openRecords(u: ManagedUser) {
  Object.assign(rec, { show: true, user: u, rows: [], loading: true })
  try { rec.rows = await accountsApi.userBacktests(u.id) } finally { rec.loading = false }
}

const cols = computed<DataTableColumns<ManagedUser>>(() => [
  { title: '学生', key: 'display_name', minWidth: 170,
    render: (u) => h('div', { class: 'who' }, [h('span', { class: 'av' }, (u.display_name || u.username).slice(0, 1)),
      h('div', [h('b', u.display_name || u.username), h('em', u.username)])]) },
  { title: '状态', key: 'disabled', width: 86,
    render: (u) => h(NTag, { size: 'small', round: true, bordered: false, type: u.disabled ? 'default' : (u.last_login ? 'success' : 'warning') },
      () => (u.disabled ? '已停用' : u.last_login ? '正常' : '未登录')) },
  { title: '今日用量', key: 'quota', width: 110,
    render: (u) => {
      const l = u.quota.limit
      const full = l !== null && u.quota.used >= l
      return h(NTooltip, null, {
        trigger: () => h('span', { class: ['use', { full }] }, [h('b', u.quota.used), ` / ${l === null ? '不限' : l}`]),
        default: () => `每日上限来自${u.quota.source}`,
      })
    } },
  { title: '平台模型', key: 'allow_platform', width: 90,
    render: (u) => h(NSwitch, { size: 'small', value: u.allow_platform, onUpdateValue: (v: boolean) => togglePlatform(u, v) }) },
  { title: '回测', key: 'backtest_count', width: 72, align: 'right', sorter: (a, b) => a.backtest_count - b.backtest_count },
  { title: '对话', key: 'chat_count', width: 72, align: 'right', sorter: (a, b) => a.chat_count - b.chat_count },
  { title: '最近登录', key: 'last_login', width: 110, render: (u) => h('span', { class: 'muted' }, u.last_login ? timeAgo(u.last_login) : '从未登录'),
    sorter: (a, b) => (a.last_login ?? '').localeCompare(b.last_login ?? '') },
  { title: '', key: 'ops', width: 56, align: 'center',
    render: (u) => h(NDropdown, { trigger: 'click', options: rowMenu(u), onSelect: (k: string) => onRow(k, u) },
      () => h(NButton, { size: 'small', quaternary: true, circle: true }, { icon: () => h(MoreHorizontal, { size: 16 }) })) },
])

// ---------------- 额度与平台模型权限
const qm = reactive({ show: false, title: '', value: null as number | null, target: null as ManagedUser | null, inheritLabel: '', hint: '' })
function editClassQuota() {
  Object.assign(qm, { show: true, title: `「${props.room.name}」学生默认每日次数`, value: props.room.quota_daily, target: null,
    inheritLabel: '沿用平台默认值（由管理员设置）', hint: '' })
}
function editUserQuota(u: ManagedUser) {
  Object.assign(qm, { show: true, title: `${u.display_name} 的每日次数`, value: u.quota_daily, target: u,
    inheritLabel: `沿用班级默认（${quotaText(props.room.quota_daily)}）`, hint: '' })
}
async function saveQuota(v: number | null) {
  try {
    if (qm.target) Object.assign(qm.target, await accountsApi.updateUser(qm.target.id, { quota_daily: v }))
    else { Object.assign(props.room, await accountsApi.updateClass(props.room.id, { quota_daily: v })); load() }
    toast.success('额度已更新')
  } catch (e: any) { toast.error(e.message) }
}
async function togglePlatform(u: ManagedUser, v: boolean) {
  try {
    Object.assign(u, await accountsApi.updateUser(u.id, { allow_platform: v }))
    toast.success(v ? `已允许 ${u.display_name} 使用平台模型` : `已关闭 ${u.display_name} 的平台模型使用权限`)
  } catch (e: any) { toast.error(e.message) }
}

const importShow = ref(false)
async function copyInvite() {
  const text = `加入「${props.room.name}」\n注册网址：${location.origin}/login\n班级邀请码：${props.room.invite_code}`
  if (await copyText(text)) toast.success('已复制注册网址和班级邀请码')
}
function exportList() {
  downloadCsv(`${props.room.name}-学生名单.csv`, [
    ['用户名', '姓名', '状态', '回测次数', '对话次数', '最近登录', '注册时间'],
    ...students.value.map((u) => [u.username, u.display_name, u.disabled ? '已停用' : '正常', u.backtest_count, u.chat_count,
      u.last_login?.slice(0, 16).replace('T', ' ') ?? '', u.created_at.slice(0, 10)]),
  ])
}
</script>

<template>
  <div class="detail">
    <button class="back" @click="emit('back')"><ArrowLeft :size="15" /> 返回班级列表</button>

    <header class="dh card">
      <div class="dh-main">
        <h2>{{ room.name }}</h2>
        <p>{{ room.description || '暂无备注' }}<template v-if="room.teacher_name"> · 负责老师：{{ room.teacher_name }}</template></p>
        <button class="quota-chip" title="设置本班学生的默认每日次数" @click="editClassQuota">
          <Gauge :size="14" /> 学生默认额度：{{ room.quota_daily === null ? '沿用平台默认' : quotaText(room.quota_daily) }}
        </button>
      </div>
      <div class="dh-ticket" :class="{ off: !room.registration_open }">
        <span>通用邀请码</span>
        <code>{{ room.invite_code }}</code>
        <button title="复制注册网址和邀请码" @click="copyInvite"><Copy :size="14" /></button>
        <em>{{ room.registration_open ? '开放注册中' : '已关闭注册' }}</em>
      </div>
    </header>

    <div class="row2">
      <section class="card card-pad">
        <h3 class="section-title">近 30 天回测次数</h3>
        <p class="section-sub">共 {{ monthTotal }} 次；鼠标停在柱子上查看当天活跃人数</p>
        <VChart v-if="activity" class="chart" :option="chart" autoresize />
      </section>
      <section class="card card-pad kpis">
        <div><b>{{ students.length }}</b><span>学生人数</span></div>
        <div><b>{{ room.active_7d }}</b><span>近 7 天登录</span></div>
        <div><b>{{ neverLogin }}</b><span>从未登录</span></div>
        <div><b>{{ room.backtest_count }}</b><span>累计回测</span></div>
        <div class="kpi-w"><b>{{ students.length ? pct(room.active_7d / students.length, 0) : '—' }}</b><span>周活跃率</span></div>
      </section>
    </div>

    <OnceCodes kind="student" :class-id="room.id" :class-name="room.name" />

    <section class="card card-pad">
      <div class="tb">
        <h3 class="section-title">学生（{{ students.length }}）</h3>
        <NInput v-model:value="q" size="small" clearable placeholder="搜索姓名或用户名" class="search"><template #prefix><Search :size="14" /></template></NInput>
        <span class="sp" />
        <NButton size="small" secondary @click="exportList" :disabled="!students.length"><template #icon><Download :size="14" /></template>导出名单</NButton>
        <NButton size="small" secondary @click="importShow = true"><template #icon><FileUp :size="14" /></template>批量导入</NButton>
        <NButton size="small" type="primary" @click="openForm()"><template #icon><UserPlus :size="14" /></template>添加学生</NButton>
      </div>
      <NEmpty v-if="!loading && !students.length" description="班级里还没有学生：可以把邀请码发给学生自行注册，或者批量导入名单" class="empty" />
      <NDataTable v-else :columns="cols" :data="list" :loading="loading" size="small" :bordered="false" :pagination="{ pageSize: 20 }" :scroll-x="820" />
    </section>

    <NModal v-model:show="form.show" preset="card" :title="form.id ? '修改学生信息' : '添加学生'" :bordered="false" style="width: 420px; max-width: calc(100vw - 32px)">
      <NForm label-placement="top" @submit.prevent="saveForm">
        <NFormItem v-if="!form.id" label="用户名（登录用）"><NInput v-model:value="form.username" :maxlength="20" placeholder="2~20 位中文、字母、数字或下划线" /></NFormItem>
        <NFormItem label="姓名"><NInput v-model:value="form.display_name" :maxlength="20" placeholder="例如：张三" /></NFormItem>
        <NFormItem v-if="!form.id" label="初始密码（选填）"><NInput v-model:value="form.password" :maxlength="64" placeholder="留空则自动生成 8 位随机密码" /></NFormItem>
        <NButton type="primary" block attr-type="submit" :loading="form.saving">{{ form.id ? '保存' : '创建账号' }}</NButton>
      </NForm>
    </NModal>

    <NModal v-model:show="move.show" preset="card" title="移到其他班级" :bordered="false" style="width: 400px; max-width: calc(100vw - 32px)">
      <p class="muted mv">把 <b>{{ move.user?.display_name }}</b> 从「{{ room.name }}」移到：</p>
      <NSelect v-model:value="move.target" :options="others" placeholder="选择班级" />
      <NButton type="primary" block class="mv-btn" :disabled="!move.target" @click="doMove">确定移动</NButton>
    </NModal>

    <NDrawer v-model:show="rec.show" :width="460" placement="right">
      <NDrawerContent :title="`${rec.user?.display_name ?? ''} 的回测记录`" closable>
        <NEmpty v-if="!rec.loading && !rec.rows.length" description="还没有回测记录" />
        <a v-for="r in rec.rows" :key="r.id" :href="`/report/${r.id}`" target="_blank" class="rec">
          <div><b>{{ r.title }}</b><em>{{ r.start }} ~ {{ r.end }} · {{ timeAgo(r.created_at) }}{{ r.source === 'chat' ? ' · 对话' : '' }}</em></div>
          <span :class="(r.summary.total_return ?? 0) >= 0 ? 'up' : 'down'">{{ pct(r.summary.total_return, 1, true) }}</span>
        </a>
      </NDrawerContent>
    </NDrawer>

    <QuotaModal v-model:show="qm.show" :title="qm.title" :value="qm.value" :inherit-label="qm.inheritLabel" @save="saveQuota" />
    <ImportModal v-model:show="importShow" :class-id="room.id" :class-name="room.name" @done="changed" />
    <PasswordReveal v-model:show="reveal.show" :username="reveal.username" :password="reveal.password" :title="reveal.title" />
  </div>
</template>

<style scoped>
.detail { display: flex; flex-direction: column; gap: 14px; }
.back { align-self: flex-start; display: inline-flex; align-items: center; gap: 4px; border: 0; background: none; color: var(--text-3); cursor: pointer; font: inherit; font-size: 13px; padding: 0; }
.back:hover { color: var(--primary); }
.dh { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 20px; flex-wrap: wrap;
  background: linear-gradient(120deg, var(--surface) 40%, var(--primary-soft)); }
.dh h2 { margin: 0; font-size: 20px; }
.dh p { margin: 4px 0 0; font-size: 13px; color: var(--text-2); }
.dh-ticket { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 10px; border: 1.5px dashed color-mix(in srgb, var(--t-amber) 55%, var(--border)); background: var(--t-amber-soft); }
.dh-ticket.off { opacity: 0.65; }
.dh-ticket span { font-size: 12px; font-weight: 650; color: var(--t-amber); }
.dh-ticket code { font-family: var(--mono); font-size: 15px; letter-spacing: 0.5px; }
.dh-ticket button { border: 0; background: none; color: var(--text-3); cursor: pointer; display: grid; padding: 3px; border-radius: 6px; }
.dh-ticket button:hover { color: var(--text-1); background: var(--surface); }
.dh-ticket em { font-style: normal; font-size: 12px; color: var(--text-3); }
.row2 { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 14px; }
.chart { height: 190px; }
.kpis { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-content: center; }
.kpis div { padding: 10px 12px; border-radius: 10px; background: var(--surface-2); }
.kpis b { display: block; font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
.kpis span { font-size: 12px; color: var(--text-3); }
.kpi-w { grid-column: span 2; }
.tb { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.tb .section-title { margin: 0; }
.search { width: 200px; }
.sp { flex: 1; }
.empty { padding: 30px 0; }
:deep(.who) { display: flex; align-items: center; gap: 10px; }
:deep(.who .av) { width: 30px; height: 30px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center; font-weight: 650; font-size: 13px; color: var(--primary-ink); background: var(--primary-soft); }
:deep(.who b) { display: block; font-size: 13.5px; font-weight: 600; }
:deep(.who em) { display: block; font-style: normal; font-size: 11.5px; color: var(--text-3); }
.mv { margin: 0 0 10px; }
.quota-chip {
  display: inline-flex; align-items: center; gap: 5px; margin-top: 8px; padding: 3px 10px; border-radius: 999px; cursor: pointer;
  font: inherit; font-size: 12.5px; color: var(--t-violet); background: var(--t-violet-soft); border: 1px dashed color-mix(in srgb, var(--t-violet) 40%, transparent);
}
.quota-chip:hover { border-style: solid; }
:deep(.use) { font-variant-numeric: tabular-nums; color: var(--text-3); }
:deep(.use b) { color: var(--text-1); font-weight: 650; }
:deep(.use.full b) { color: var(--up); }
.mv-btn { margin-top: 14px; }
.rec { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 10px; color: var(--text-1); border: 1px solid var(--border); margin-bottom: 8px; transition: background 0.15s; }
.rec:hover { background: var(--surface-2); }
.rec > div { flex: 1; min-width: 0; }
.rec b { display: block; font-size: 13.5px; font-weight: 600; }
.rec em { display: block; font-style: normal; font-size: 12px; color: var(--text-3); }
.rec span { font-weight: 650; font-variant-numeric: tabular-nums; }
@media (max-width: 900px) { .row2 { grid-template-columns: 1fr; } }
</style>
