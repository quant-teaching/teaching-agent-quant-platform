<script setup lang="ts">
// 班级管理：卡片网格展示每个班级的人数、活跃度、回测量和邀请码；点击进入班级详情管理学生
import { Activity, Copy, FlaskConical, MoreHorizontal, Plus, RefreshCw, School, Trash2, Pencil, Users } from 'lucide-vue-next'
import { NButton, NDropdown, NEmpty, NForm, NFormItem, NInput, NModal, NSelect, NSpin, NSwitch, useDialog, useMessage } from 'naive-ui'
import { computed, h, onMounted, reactive, ref } from 'vue'
import { accountsApi, copyText, type ClassInfo, type ManagedUser } from '@/api/accounts'
import { useAuth } from '@/stores/auth'
import ClassDetail from './ClassDetail.vue'

const auth = useAuth()
const toast = useMessage()
const dialog = useDialog()
const classes = ref<ClassInfo[]>([])
const teachers = ref<ManagedUser[]>([])
const loading = ref(true)
const openId = ref<number | null>(null)
const isAdmin = computed(() => auth.user?.role === 'admin')

async function load() {
  loading.value = true
  try {
    classes.value = await accountsApi.classes()
    if (isAdmin.value) teachers.value = (await accountsApi.users()).filter((u) => u.role !== 'student')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const totals = computed(() => ({
  classes: classes.value.length,
  students: classes.value.reduce((n, c) => n + c.student_count, 0),
  active: classes.value.reduce((n, c) => n + c.active_7d, 0),
  backtests: classes.value.reduce((n, c) => n + c.backtest_count, 0),
}))

// 新建 / 编辑
const form = reactive({ show: false, id: null as number | null, name: '', description: '', teacher_id: null as number | null, saving: false })
function openForm(c?: ClassInfo) {
  Object.assign(form, { show: true, id: c?.id ?? null, name: c?.name ?? '', description: c?.description ?? '',
    teacher_id: c?.teacher_id ?? auth.user?.id ?? null })
}
async function saveForm() {
  if (!form.name.trim()) return toast.error('请填写班级名称')
  form.saving = true
  try {
    const body: any = { name: form.name.trim(), description: form.description.trim() }
    if (isAdmin.value && form.teacher_id) body.teacher_id = form.teacher_id
    if (form.id) await accountsApi.updateClass(form.id, body)
    else {
      const c = await accountsApi.createClass(body)
      toast.success(`已创建「${c.name}」，邀请码 ${c.invite_code}`)
    }
    form.show = false
    await load()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    form.saving = false
  }
}

async function toggleReg(c: ClassInfo, v: boolean) {
  try {
    Object.assign(c, await accountsApi.updateClass(c.id, { registration_open: v }))
    toast.success(v ? `「${c.name}」已开放注册` : `「${c.name}」已关闭注册`)
  } catch (e: any) { toast.error(e.message) }
}
async function copyInvite(c: ClassInfo) {
  const text = `加入「${c.name}」\n注册网址：${location.origin}/login\n班级邀请码：${c.invite_code}`
  if (await copyText(text)) toast.success('已复制注册网址和班级邀请码')
  else toast.info(text)
}
function regenerate(c: ClassInfo) {
  dialog.warning({
    title: '更换邀请码', content: `更换后旧邀请码「${c.invite_code}」立即失效，已注册的学生不受影响。确定更换吗？`,
    positiveText: '更换', negativeText: '取消',
    onPositiveClick: async () => { Object.assign(c, await accountsApi.regenerate(c.id)); toast.success(`新邀请码：${c.invite_code}`) },
  })
}
function remove(c: ClassInfo) {
  dialog.error({
    title: '删除班级', content: c.student_count ? `「${c.name}」还有 ${c.student_count} 名学生，需要先把学生移到其他班级或删除。` : `确定删除「${c.name}」吗？`,
    positiveText: c.student_count ? '知道了' : '删除', negativeText: c.student_count ? undefined : '取消',
    onPositiveClick: async () => {
      if (c.student_count) return
      try { await accountsApi.deleteClass(c.id); toast.success('已删除'); await load() } catch (e: any) { toast.error(e.message) }
    },
  })
}
const menu = [
  { key: 'edit', label: '编辑班级', icon: () => h(Pencil, { size: 14 }) },
  { key: 'regen', label: '更换邀请码', icon: () => h(RefreshCw, { size: 14 }) },
  { type: 'divider', key: 'd' },
  { key: 'delete', label: '删除班级', icon: () => h(Trash2, { size: 14 }) },
]
function onMenu(key: string, c: ClassInfo) {
  if (key === 'edit') openForm(c)
  else if (key === 'regen') regenerate(c)
  else if (key === 'delete') remove(c)
}
const TONES = ['blue', 'violet', 'teal', 'amber', 'rose', 'green']
const openClass = computed(() => classes.value.find((c) => c.id === openId.value) ?? null)
</script>

<template>
  <div class="panel-body">
    <Transition name="learn-swap" mode="out-in">
      <ClassDetail v-if="openClass" :key="openClass.id" :room="openClass" :classes="classes" @back="openId = null; load()" @changed="load" />

      <div v-else key="list">
        <div class="head">
          <div>
            <h3 class="section-title"><School :size="16" class="ti" /> {{ isAdmin ? '全部班级' : '我的班级' }}</h3>
            <p class="section-sub">每个班级有独立的邀请码，学生注册时填写邀请码即进入该班级。班级之间互相隔离，学生只能看到同班同学分享的报告。</p>
          </div>
          <NButton type="primary" @click="openForm()"><template #icon><Plus :size="16" /></template>新建班级</NButton>
        </div>

        <div class="totals">
          <div class="tot tone-blue"><span class="ic-tile"><School :size="16" /></span><div><b>{{ totals.classes }}</b><em>班级</em></div></div>
          <div class="tot tone-violet"><span class="ic-tile"><Users :size="16" /></span><div><b>{{ totals.students }}</b><em>学生</em></div></div>
          <div class="tot tone-teal"><span class="ic-tile"><Activity :size="16" /></span><div><b>{{ totals.active }}</b><em>近 7 天登录</em></div></div>
          <div class="tot tone-amber"><span class="ic-tile"><FlaskConical :size="16" /></span><div><b>{{ totals.backtests }}</b><em>累计回测</em></div></div>
        </div>

        <NSpin :show="loading">
          <NEmpty v-if="!loading && !classes.length" description="还没有班级，点右上角「新建班级」创建第一个" class="empty" />
          <div class="grid stagger">
            <article v-for="(c, i) in classes" :key="c.id" class="cls card" :class="`tone-${TONES[i % TONES.length]}`" @click="openId = c.id">
              <header>
                <span class="cls-ic"><School :size="18" /></span>
                <div class="cls-t">
                  <b>{{ c.name }}</b>
                  <em>{{ c.description || (c.teacher_name ? `负责老师：${c.teacher_name}` : '未指定负责老师') }}</em>
                </div>
                <NDropdown trigger="click" :options="menu" @select="(k: string) => onMenu(k, c)">
                  <button class="more" title="更多操作" @click.stop><MoreHorizontal :size="17" /></button>
                </NDropdown>
              </header>
              <div class="stats">
                <div><b>{{ c.student_count }}</b><span>学生</span></div>
                <div><b>{{ c.active_7d }}</b><span>近 7 天登录</span></div>
                <div><b>{{ c.backtest_count }}</b><span>回测次数</span></div>
              </div>
              <div class="bar" :title="`近 7 天登录 ${c.active_7d} / ${c.student_count}`">
                <span :style="{ width: c.student_count ? `${(c.active_7d / c.student_count) * 100}%` : '0%' }" />
              </div>
              <div class="ticket" :class="{ off: !c.registration_open }" @click.stop>
                <span class="tk-l">通用邀请码</span>
                <code>{{ c.invite_code }}</code>
                <button title="复制注册网址和邀请码" @click="copyInvite(c)"><Copy :size="14" /></button>
                <label class="tk-sw"><NSwitch size="small" :value="c.registration_open" @update:value="(v: boolean) => toggleReg(c, v)" />{{ c.registration_open ? '开放注册' : '已关闭' }}</label>
              </div>
              <footer>
                <span v-if="isAdmin && c.teacher_name" class="muted">负责老师：{{ c.teacher_name }}</span>
                <span v-if="c.disabled_count" class="muted">停用 {{ c.disabled_count }} 人</span>
                <span class="go">管理学生 →</span>
              </footer>
            </article>
          </div>
        </NSpin>
      </div>
    </Transition>

    <NModal v-model:show="form.show" preset="card" :title="form.id ? '编辑班级' : '新建班级'" :bordered="false" style="width: 440px; max-width: calc(100vw - 32px)">
      <NForm label-placement="top" @submit.prevent="saveForm">
        <NFormItem label="班级名称"><NInput v-model:value="form.name" :maxlength="30" placeholder="例如：2026 春 量化投资一班" /></NFormItem>
        <NFormItem label="备注（选填）"><NInput v-model:value="form.description" :maxlength="100" placeholder="例如：周三下午 3-4 节" /></NFormItem>
        <NFormItem v-if="isAdmin" label="负责老师">
          <NSelect v-model:value="form.teacher_id" :options="teachers.map((t) => ({ label: `${t.display_name}（${t.role_label}）`, value: t.id }))" />
        </NFormItem>
        <p v-if="!form.id" class="muted hint">创建后会自动生成班级邀请码，学生用它注册即可进入本班。</p>
        <NButton type="primary" block attr-type="submit" :loading="form.saving">{{ form.id ? '保存' : '创建班级' }}</NButton>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 14px; }
.ti { vertical-align: -2px; margin-right: 2px; }
.totals { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.tot { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); }
.tot b { display: block; font-size: 20px; font-weight: 700; line-height: 1.2; font-variant-numeric: tabular-nums; }
.tot em { font-style: normal; font-size: 12px; color: var(--text-3); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.cls { position: relative; overflow: hidden; padding: 16px 18px 14px; cursor: pointer; display: flex; flex-direction: column; gap: 12px; }
.cls::before { content: ""; position: absolute; inset: 0 0 auto; height: 3px; background: var(--tone); }
.cls:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); border-color: color-mix(in srgb, var(--tone) 45%, var(--border)); }
.cls header { display: flex; align-items: center; gap: 12px; }
.cls-ic { width: 38px; height: 38px; flex-shrink: 0; border-radius: 11px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(140deg, color-mix(in srgb, var(--tone) 70%, #fff), var(--tone)); }
.cls-t { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.cls-t b { font-size: 15.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cls-t em { font-style: normal; font-size: 12px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.more { width: 30px; height: 30px; border: 0; border-radius: 8px; display: grid; place-items: center; background: none; color: var(--text-3); cursor: pointer; }
.more:hover { background: var(--surface-3); color: var(--text-1); }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); text-align: center; }
.stats b { display: block; font-size: 22px; font-weight: 700; color: var(--tone); font-variant-numeric: tabular-nums; }
.stats span { font-size: 11.5px; color: var(--text-3); }
.bar { height: 5px; border-radius: 5px; background: var(--surface-3); overflow: hidden; }
.bar span { display: block; height: 100%; border-radius: 5px; background: var(--tone); transition: width 0.6s var(--ease-out); }
.ticket {
  display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 10px; cursor: default;
  border: 1.5px dashed color-mix(in srgb, var(--tone) 45%, var(--border)); background: var(--tone-soft);
}
.ticket.off { opacity: 0.65; }
.tk-l { font-size: 11.5px; font-weight: 650; color: var(--tone); }
.ticket code { flex: 1; font-family: var(--mono); font-size: 13.5px; letter-spacing: 0.5px; color: var(--text-1); }
.ticket button { border: 0; background: none; color: var(--text-3); cursor: pointer; display: grid; padding: 3px; border-radius: 6px; }
.ticket button:hover { color: var(--text-1); background: var(--surface); }
.tk-sw { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); white-space: nowrap; }
.cls footer { display: flex; gap: 10px; font-size: 12px; }
.go { margin-left: auto; color: var(--tone); font-weight: 600; }
.empty { padding: 40px 0; }
.hint { margin: -4px 0 14px; font-size: 12.5px; }
@media (max-width: 900px) { .totals { grid-template-columns: repeat(2, minmax(0, 1fr)); } .head { flex-direction: column; } }
</style>
