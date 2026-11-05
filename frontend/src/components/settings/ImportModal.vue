<script setup lang="ts">
// 批量导入学生：① 下载模板填写 → ② 选择文件预览校验 → ③ 确认创建，下载账号清单（含初始密码）
import { CircleAlert, CircleCheck, Download, FileSpreadsheet, Upload } from 'lucide-vue-next'
import { NButton, NDataTable, NModal, NSteps, NStep, useMessage, type DataTableColumns } from 'naive-ui'
import { computed, h, ref, watch } from 'vue'
import { accountsApi, downloadCsv, fileToBase64, type ImportResult, type ImportRow } from '@/api/accounts'

const props = defineProps<{ classId: number; className: string }>()
const show = defineModel<boolean>('show', { default: false })
const emit = defineEmits<{ done: [] }>()
const toast = useMessage()

const step = ref(1)
const file = ref<File | null>(null)
const content = ref('')
const preview = ref<ImportResult | null>(null)
const result = ref<ImportResult | null>(null)
const busy = ref(false)
const dragging = ref(false)
const input = ref<HTMLInputElement | null>(null)

watch(show, (v) => { if (v) reset() })
function reset() {
  step.value = 1
  file.value = null
  content.value = ''
  preview.value = null
  result.value = null
}

async function pick(f: File | undefined | null) {
  if (!f) return
  if (!/\.(csv|xlsx|xlsm)$/i.test(f.name)) return toast.error('请选择 .csv 或 .xlsx 文件')
  if (f.size > 2 * 1024 * 1024) return toast.error('文件不能超过 2 MB')
  busy.value = true
  try {
    file.value = f
    content.value = await fileToBase64(f)
    preview.value = await accountsApi.importStudents(props.classId, f.name, content.value, true)
    step.value = 2
  } catch (e: any) {
    toast.error(e.message)
    file.value = null
  } finally {
    busy.value = false
  }
}
function onDrop(e: DragEvent) {
  dragging.value = false
  pick(e.dataTransfer?.files?.[0])
}

async function confirm() {
  if (!file.value) return
  busy.value = true
  try {
    result.value = await accountsApi.importStudents(props.classId, file.value.name, content.value, false)
    step.value = 3
    toast.success(`已创建 ${result.value.valid} 个学生账号`)
    emit('done')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

function downloadAccounts() {
  if (!result.value) return
  const rows = result.value.rows.filter((r) => !r.error)
  downloadCsv(`${props.className}-账号清单.csv`, [
    ['班级', '用户名', '姓名', '初始密码', '登录网址'],
    ...rows.map((r) => [props.className, r.username, r.display_name, r.password, `${location.origin}/login`]),
  ])
}

const bad = computed(() => (preview.value ? preview.value.total - preview.value.valid : 0))
const cols = computed<DataTableColumns<ImportRow>>(() => [
  { title: '行号', key: 'row', width: 64 },
  { title: '用户名', key: 'username', minWidth: 120 },
  { title: '姓名', key: 'display_name', minWidth: 90 },
  { title: step.value === 3 ? '初始密码' : '密码', key: 'password', minWidth: 140,
    render: (r) => h('span', { class: step.value === 3 && !r.error ? 'pw' : 'muted' }, r.error ? '—' : r.password) },
  { title: '校验', key: 'error', minWidth: 200,
    render: (r) => r.error
      ? h('span', { class: 'row-err' }, [h(CircleAlert, { size: 14 }), r.error])
      : h('span', { class: 'row-ok' }, [h(CircleCheck, { size: 14 }), step.value === 3 ? '已创建' : '可以导入']) },
])
const rows = computed(() => (step.value === 3 ? result.value?.rows : preview.value?.rows) ?? [])
</script>

<template>
  <NModal v-model:show="show" preset="card" :title="`批量导入学生 · ${className}`" :bordered="false" style="width: 760px; max-width: calc(100vw - 32px)">
    <NSteps :current="step" size="small" class="steps">
      <NStep title="选择名单" description="下载模板并填写" />
      <NStep title="预览校验" description="检查每一行" />
      <NStep title="完成" description="下载账号清单" />
    </NSteps>

    <!-- 第 1 步 -->
    <div v-if="step === 1" class="s1">
      <div class="tpl">
        <FileSpreadsheet :size="28" />
        <div>
          <b>第一次导入？先下载模板</b>
          <p>模板有三列：<code>用户名</code>（必填，2~20 位中文、字母、数字或下划线）、<code>姓名</code>（选填）、<code>初始密码</code>（选填，留空自动生成 8 位密码）。用 Excel 填写后直接保存即可，支持 .csv 和 .xlsx。</p>
        </div>
        <NButton tag="a" href="/api/users/import-template" download secondary><template #icon><Download :size="15" /></template>下载模板</NButton>
      </div>
      <div class="drop" :class="{ on: dragging, busy }" @click="input?.click()" @dragover.prevent="dragging = true"
        @dragleave="dragging = false" @drop.prevent="onDrop">
        <Upload :size="30" />
        <b>{{ busy ? '正在读取…' : '点击选择文件，或把文件拖到这里' }}</b>
        <span>支持 .csv / .xlsx，最多 500 人，不超过 2 MB</span>
        <input ref="input" type="file" accept=".csv,.xlsx,.xlsm" hidden @change="pick(($event.target as HTMLInputElement).files?.[0])" />
      </div>
    </div>

    <!-- 第 2、3 步 -->
    <div v-else class="s2">
      <div class="sum" :class="{ done: step === 3 }">
        <template v-if="step === 2 && preview">
          <span>文件 <b>{{ file?.name }}</b> 共 <b>{{ preview.total }}</b> 行，<b class="ok">{{ preview.valid }}</b> 行可以导入<template v-if="bad">，<b class="err">{{ bad }}</b> 行有问题（不会导入）</template></span>
        </template>
        <template v-else-if="result">
          <CircleCheck :size="18" />
          <span>已在「{{ className }}」创建 <b>{{ result.valid }}</b> 个学生账号。初始密码只显示这一次，请下载账号清单分发给学生。</span>
        </template>
      </div>
      <NDataTable :columns="cols" :data="rows" size="small" :max-height="320" :bordered="false" striped :row-key="(r: ImportRow) => r.row" />
      <div class="acts">
        <template v-if="step === 2">
          <NButton @click="reset">重新选择文件</NButton>
          <NButton type="primary" :loading="busy" :disabled="!preview?.valid" @click="confirm">导入 {{ preview?.valid ?? 0 }} 个账号</NButton>
        </template>
        <template v-else>
          <NButton @click="show = false">完成</NButton>
          <NButton type="primary" @click="downloadAccounts"><template #icon><Download :size="15" /></template>下载账号清单</NButton>
        </template>
      </div>
    </div>
  </NModal>
</template>

<style scoped>
.steps { margin-bottom: 18px; }
.s1 { display: flex; flex-direction: column; gap: 14px; }
.tpl { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-radius: 12px; background: var(--t-teal-soft); color: var(--t-teal); }
.tpl b { color: var(--text-1); font-size: 14px; }
.tpl p { margin: 4px 0 0; font-size: 12.5px; color: var(--text-2); line-height: 1.6; }
.tpl code { font-family: var(--mono); font-size: 12px; padding: 0 4px; border-radius: 4px; background: var(--surface); }
.tpl > div { flex: 1; }
.drop {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 34px 20px; border-radius: 14px; cursor: pointer;
  border: 2px dashed var(--border-strong); color: var(--text-3); background: var(--surface-2); transition: border-color 0.2s, background 0.2s, color 0.2s;
}
.drop:hover, .drop.on { border-color: var(--primary); color: var(--primary); background: var(--primary-soft); }
.drop.busy { pointer-events: none; opacity: 0.7; }
.drop b { color: var(--text-1); font-size: 14px; }
.drop span { font-size: 12px; }
.s2 { display: flex; flex-direction: column; gap: 12px; }
.sum { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 10px; font-size: 13px; background: var(--surface-2); }
.sum.done { color: var(--c-tip); background: var(--c-tip-soft); }
.sum b.ok { color: var(--c-tip); }
.sum b.err { color: var(--up); }
.acts { display: flex; justify-content: flex-end; gap: 10px; }
:deep(.row-err) { display: inline-flex; align-items: center; gap: 4px; color: var(--up); }
:deep(.row-ok) { display: inline-flex; align-items: center; gap: 4px; color: var(--c-tip); }
:deep(.pw) { font-family: var(--mono); color: var(--primary-ink); }
</style>
