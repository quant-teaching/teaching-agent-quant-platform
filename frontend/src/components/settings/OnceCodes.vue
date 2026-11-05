<script setup lang="ts">
// 一次性注册码：每个码只能注册一个账号，用过即失效。学生码属于某个班级，老师码由管理员生成
import { Ban, Copy, Download, KeyRound, Plus, Search, Tag, Trash2, X } from 'lucide-vue-next'
import { NButton, NDataTable, NInput, NInputNumber, NModal, NRadioButton, NRadioGroup, NSelect, NTag, useDialog, useMessage, type DataTableColumns, type DataTableRowKey } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { accountsApi, copyText, downloadCsv, type OnceCode } from '@/api/accounts'
import { timeAgo } from '@/utils/format'

const props = defineProps<{ kind: 'student' | 'teacher'; classId?: number; className?: string }>()
const toast = useMessage()
const dialog = useDialog()
const codes = ref<OnceCode[]>([])
const loading = ref(true)
const count = ref(10)
const note = ref('')
const busy = ref(false)
const filter = ref<'unused' | 'used' | 'revoked' | 'all'>('unused')

async function load() {
  loading.value = true
  try {
    codes.value = props.kind === 'teacher' ? await accountsApi.teacherCodes() : await accountsApi.classCodes(props.classId!)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const counts = computed(() => ({
  unused: codes.value.filter((c) => c.state === 'unused').length,
  used: codes.value.filter((c) => c.state === 'used').length,
  revoked: codes.value.filter((c) => c.state === 'revoked').length,
}))
// 按批次（备注）和关键词筛选；生成时填写的备注就是批次名
const batch = ref<string | null>(null)
const q = ref('')
const batches = computed(() => {
  const m = new Map<string, number>()
  for (const c of codes.value) m.set(c.note, (m.get(c.note) ?? 0) + 1)
  return [...m.entries()].map(([n, k]) => ({ label: `${n || '（无备注）'} · ${k} 个`, value: n }))
})
const list = computed(() => {
  const k = q.value.trim().toUpperCase()
  return codes.value.filter((c) => (filter.value === 'all' || c.state === filter.value)
    && (batch.value === null || c.note === batch.value)
    && (!k || c.code.includes(k) || c.note.toUpperCase().includes(k) || (c.used_by_name ?? '').toUpperCase().includes(k)))
})

// ---------------- 批量操作
const checked = ref<DataTableRowKey[]>([])
const selected = computed(() => codes.value.filter((c) => checked.value.includes(c.code)))
const selUnused = computed(() => selected.value.filter((c) => c.state === 'unused'))
const selUsed = computed(() => selected.value.filter((c) => c.state === 'used').length)
function clearSel() { checked.value = [] }
async function batchCopy() {
  const rows = selUnused.value.map((c) => c.code)
  if (!rows.length) return toast.info('所选注册码中没有未使用的')
  if (await copyText(rows.join('\n'))) toast.success(`已复制 ${rows.length} 个未使用的注册码，每行一个`)
}
async function runBatch(action: 'revoke' | 'delete' | 'note', noteText = '') {
  try {
    const r = await accountsApi.batchCodes(selected.value.map((c) => c.code), action, noteText)
    const verb = { revoke: '作废', delete: '删除', note: '修改备注' }[action]
    toast.success(`已${verb} ${r.done} 个${r.skipped ? `，跳过 ${r.skipped} 个（已使用的码会保留作为注册记录）` : ''}`)
    clearSel()
    await load()
  } catch (e: any) { toast.error(e.message) }
}
function batchRevoke() {
  dialog.warning({
    title: '批量作废', content: `作废所选 ${selected.value.length} 个注册码？其中已使用的 ${selUsed.value} 个会被跳过。`,
    positiveText: '作废', negativeText: '取消', onPositiveClick: () => runBatch('revoke'),
  })
}
function batchDelete() {
  dialog.error({
    title: '批量删除', content: `删除所选 ${selected.value.length} 个注册码？删除后无法恢复；已使用的 ${selUsed.value} 个会保留作为注册记录。`,
    positiveText: '删除', negativeText: '取消', onPositiveClick: () => runBatch('delete'),
  })
}
const noteDlg = ref({ show: false, text: '' })
function batchNote() { noteDlg.value = { show: true, text: selected.value[0]?.note ?? '' } }
function saveNote() { noteDlg.value.show = false; runBatch('note', noteDlg.value.text) }

async function create() {
  busy.value = true
  try {
    const made = props.kind === 'teacher'
      ? await accountsApi.createTeacherCodes(count.value, note.value)
      : await accountsApi.createClassCodes(props.classId!, count.value, note.value)
    toast.success(`已生成 ${made.length} 个一次性注册码`)
    batch.value = note.value || null
    note.value = ''
    filter.value = 'unused'
    clearSel()
    await load()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}
const who = computed(() => (props.kind === 'teacher' ? '老师' : '学生'))
const howTo = computed(() => (props.kind === 'teacher' ? '「注册 → 我是老师」' : '「注册 → 我是学生」'))
async function copyOne(c: OnceCode) {
  const text = `注册网址：${location.origin}/login（选择${howTo.value}）\n一次性注册码：${c.code}`
  if (await copyText(text)) toast.success('已复制注册网址和注册码')
}
async function copyUnused() {
  const rows = codes.value.filter((c) => c.state === 'unused').map((c) => c.code)
  if (!rows.length) return toast.info('没有未使用的注册码')
  if (await copyText(rows.join('\n'))) toast.success(`已复制 ${rows.length} 个未使用的注册码，每行一个`)
}
function exportCsv(only?: OnceCode[]) {
  const STATE = { unused: '未使用', used: '已使用', revoked: '已作废' }
  const rows = only ?? codes.value
  downloadCsv(`${props.className ?? '教师'}-一次性注册码.csv`, [
    ['注册码', '状态', '备注', '使用者', '使用时间', '生成时间', '注册网址'],
    ...rows.map((c) => [c.code, STATE[c.state], c.note, c.used_by_name ?? '', c.used_at?.slice(0, 16).replace('T', ' ') ?? '',
      c.created_at.slice(0, 16).replace('T', ' '), `${location.origin}/login`]),
  ])
}
function revoke(c: OnceCode) {
  dialog.warning({
    title: '作废注册码', content: `作废后「${c.code}」不能再用于注册。确定作废吗？`, positiveText: '作废', negativeText: '取消',
    onPositiveClick: async () => { await accountsApi.revokeCode(c.code); toast.success('已作废'); load() },
  })
}
const TAG = { unused: ['success', '未使用'], used: ['info', '已使用'], revoked: ['default', '已作废'] } as const
const cols: DataTableColumns<OnceCode> = [
  { type: 'selection' },
  { title: '注册码', key: 'code', width: 130, render: (c) => h('code', { class: ['oc', c.state] }, c.code) },
  { title: '状态', key: 'state', width: 82, render: (c) => h(NTag, { size: 'small', round: true, bordered: false, type: TAG[c.state][0] }, () => TAG[c.state][1]) },
  { title: '备注', key: 'note', minWidth: 90, render: (c) => h('span', { class: c.note ? '' : 'muted' }, c.note || '—') },
  { title: '使用者', key: 'used_by_name', minWidth: 110,
    render: (c) => (c.used_by_name ? h('span', [c.used_by_name, h('em', { class: 'muted when' }, ` · ${timeAgo(c.used_at!)}`)]) : h('span', { class: 'muted' }, '—')) },
  { title: '', key: 'ops', width: 84, align: 'right',
    render: (c) => h('div', { class: 'ops' }, c.state === 'unused' ? [
      h(NButton, { size: 'tiny', quaternary: true, title: '复制', onClick: () => copyOne(c) }, { icon: () => h(Copy, { size: 14 }) }),
      h(NButton, { size: 'tiny', quaternary: true, title: '作废', onClick: () => revoke(c) }, { icon: () => h(Ban, { size: 14 }) }),
    ] : []) },
]
</script>

<template>
  <section class="card card-pad oc-card">
    <div class="oc-head">
      <div>
        <h3 class="section-title"><KeyRound :size="16" class="ti" /> 一次性注册码</h3>
        <p class="section-sub">每个码只能注册一个{{ who }}账号，用过即失效，适合逐个发放、防止外传。{{ kind === 'student' ? '不受班级「开放注册」开关影响。' : '' }}</p>
      </div>
      <div class="oc-gen">
        <NInputNumber v-model:value="count" :min="1" :max="200" size="small" class="num"><template #suffix>个</template></NInputNumber>
        <NInput v-model:value="note" size="small" :maxlength="40" placeholder="备注（选填）" class="note" />
        <NButton size="small" type="primary" :loading="busy" @click="create"><template #icon><Plus :size="14" /></template>生成</NButton>
      </div>
    </div>
    <div class="oc-tb">
      <NRadioGroup v-model:value="filter" size="small">
        <NRadioButton value="unused">未使用 {{ counts.unused }}</NRadioButton>
        <NRadioButton value="used">已使用 {{ counts.used }}</NRadioButton>
        <NRadioButton value="revoked">已作废 {{ counts.revoked }}</NRadioButton>
        <NRadioButton value="all">全部</NRadioButton>
      </NRadioGroup>
      <span class="sp" />
      <NButton size="small" secondary :disabled="!counts.unused" @click="copyUnused"><template #icon><Copy :size="14" /></template>复制全部未使用</NButton>
      <NButton size="small" secondary :disabled="!codes.length" @click="exportCsv()"><template #icon><Download :size="14" /></template>下载表格</NButton>
    </div>
    <div class="oc-tb">
      <NSelect v-model:value="batch" :options="batches" clearable size="small" placeholder="按批次（备注）筛选" class="bs" />
      <NInput v-model:value="q" size="small" clearable placeholder="搜索注册码、备注或使用者" class="qs"><template #prefix><Search :size="14" /></template></NInput>
    </div>
    <Transition name="learn-swap">
      <div v-if="checked.length" class="bulk">
        <span>已选 <b>{{ checked.length }}</b> 个<template v-if="selUsed">（其中已使用 {{ selUsed }} 个）</template></span>
        <span class="sp" />
        <NButton size="small" @click="batchCopy"><template #icon><Copy :size="14" /></template>复制</NButton>
        <NButton size="small" @click="exportCsv(selected)"><template #icon><Download :size="14" /></template>导出</NButton>
        <NButton size="small" @click="batchNote"><template #icon><Tag :size="14" /></template>改备注</NButton>
        <NButton size="small" @click="batchRevoke"><template #icon><Ban :size="14" /></template>作废</NButton>
        <NButton size="small" type="error" secondary @click="batchDelete"><template #icon><Trash2 :size="14" /></template>删除</NButton>
        <NButton size="small" quaternary circle title="取消选择" @click="clearSel"><template #icon><X :size="14" /></template></NButton>
      </div>
    </Transition>
    <NDataTable v-model:checked-row-keys="checked" :columns="cols" :data="list" :loading="loading" size="small" :bordered="false"
      :max-height="340" :scroll-x="600" :row-key="(c: OnceCode) => c.code" :pagination="{ pageSize: 50 }" />
    <NModal v-model:show="noteDlg.show" preset="card" title="批量修改备注" :bordered="false" style="width: 380px; max-width: calc(100vw - 32px)">
      <p class="muted nd">把所选 {{ checked.length }} 个注册码的备注（批次名）改为：</p>
      <NInput v-model:value="noteDlg.text" :maxlength="40" placeholder="例如：3 月补录" @keydown.enter="saveNote" />
      <NButton type="primary" block class="nd-btn" @click="saveNote">保存</NButton>
    </NModal>
  </section>
</template>

<style scoped>
.oc-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.ti { vertical-align: -2px; margin-right: 2px; }
.oc-gen { display: flex; gap: 8px; align-items: center; }
.num { width: 110px; }
.note { width: 160px; }
.oc-tb { display: flex; align-items: center; gap: 8px; margin: 6px 0 10px; flex-wrap: wrap; }
.sp { flex: 1; }
.bs { width: 220px; }
.qs { width: 220px; }
.bulk {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; padding: 8px 10px; border-radius: 10px;
  background: var(--primary-soft); border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent); font-size: 13px;
}
.bulk b { color: var(--primary-ink); }
.nd { margin: 0 0 10px; }
.nd-btn { margin-top: 14px; }
:deep(.oc) { font-family: var(--mono); font-size: 13px; letter-spacing: 1px; padding: 1px 6px; border-radius: 5px; background: var(--surface-3); }
:deep(.oc.unused) { color: var(--c-tip); background: var(--c-tip-soft); }
:deep(.oc.revoked) { text-decoration: line-through; opacity: 0.6; }
:deep(.when) { font-style: normal; font-size: 12px; }
:deep(.ops) { display: inline-flex; gap: 2px; }
</style>
