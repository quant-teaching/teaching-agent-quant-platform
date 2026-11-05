<script setup lang="ts">
// 一次性注册码：每个码只能注册一个账号，用过即失效。学生码属于某个班级，老师码由管理员生成
import { Ban, Copy, Download, KeyRound, Plus } from 'lucide-vue-next'
import { NButton, NDataTable, NInput, NInputNumber, NRadioButton, NRadioGroup, NTag, useDialog, useMessage, type DataTableColumns } from 'naive-ui'
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
const list = computed(() => (filter.value === 'all' ? codes.value : codes.value.filter((c) => c.state === filter.value)))

async function create() {
  busy.value = true
  try {
    const made = props.kind === 'teacher'
      ? await accountsApi.createTeacherCodes(count.value, note.value)
      : await accountsApi.createClassCodes(props.classId!, count.value, note.value)
    toast.success(`已生成 ${made.length} 个一次性注册码`)
    note.value = ''
    filter.value = 'unused'
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
function exportCsv() {
  const STATE = { unused: '未使用', used: '已使用', revoked: '已作废' }
  downloadCsv(`${props.className ?? '教师'}-一次性注册码.csv`, [
    ['注册码', '状态', '备注', '使用者', '使用时间', '生成时间', '注册网址'],
    ...codes.value.map((c) => [c.code, STATE[c.state], c.note, c.used_by_name ?? '', c.used_at?.slice(0, 16).replace('T', ' ') ?? '',
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
      <NButton size="small" secondary :disabled="!codes.length" @click="exportCsv"><template #icon><Download :size="14" /></template>下载表格</NButton>
    </div>
    <NDataTable :columns="cols" :data="list" :loading="loading" size="small" :bordered="false" :max-height="300" :scroll-x="560"
      :row-key="(c: OnceCode) => c.code" />
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
:deep(.oc) { font-family: var(--mono); font-size: 13px; letter-spacing: 1px; padding: 1px 6px; border-radius: 5px; background: var(--surface-3); }
:deep(.oc.unused) { color: var(--c-tip); background: var(--c-tip-soft); }
:deep(.oc.revoked) { text-decoration: line-through; opacity: 0.6; }
:deep(.when) { font-style: normal; font-size: 12px; }
:deep(.ops) { display: inline-flex; gap: 2px; }
</style>
