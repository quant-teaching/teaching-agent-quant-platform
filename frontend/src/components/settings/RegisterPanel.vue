<script setup lang="ts">
// 注册设置（管理员）：教师注册码。学生的注册由各班级的邀请码控制（见「班级管理」）
import { Copy, Dices, GraduationCap, Presentation } from 'lucide-vue-next'
import { NButton, NInput, NSwitch, NTag, NTooltip, useMessage } from 'naive-ui'
import { computed, onMounted, reactive } from 'vue'
import { accountsApi, copyText } from '@/api/accounts'

const toast = useMessage()
const inv = reactive({ code: '', enabled: false, source: 'env', saved: { code: '', enabled: false }, saving: false })
const dirty = computed(() => inv.code !== inv.saved.code || inv.enabled !== inv.saved.enabled)
const valid = computed(() => /^[A-Za-z0-9_-]{4,40}$/.test(inv.code))

async function load() {
  const r = await accountsApi.teacherInvite()
  Object.assign(inv, { code: r.code, enabled: r.enabled, source: r.source, saved: { code: r.code, enabled: r.enabled } })
}
onMounted(load)
function gen() {
  const abc = 'abcdefghjkmnpqrstuvwxyz23456789'
  inv.code = 'teach-' + Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => abc[b % abc.length]).join('')
  if (!inv.enabled) inv.enabled = true
}
async function save() {
  inv.saving = true
  try {
    const r = await accountsApi.setTeacherInvite(inv.code.trim(), inv.enabled)
    Object.assign(inv, { code: r.code, enabled: r.enabled, source: r.source, saved: { code: r.code, enabled: r.enabled } })
    toast.success(r.enabled ? '教师注册码已更新，立即生效' : '已关闭老师注册')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    inv.saving = false
  }
}
async function copy() {
  const text = `量化策略教学平台 · 老师注册\n网址：${location.origin}/login（选择「注册 → 我是老师」）\n教师注册码：${inv.saved.code}`
  if (await copyText(text)) toast.success('已复制，可以直接发给老师')
  else toast.info(text)
}
</script>

<template>
  <div class="panel-body">
    <section class="card card-pad">
      <div class="head">
        <div>
          <h3 class="section-title"><Presentation :size="16" class="ti" /> 教师注册码</h3>
          <p class="section-sub">老师在登录页选择「注册 → 我是老师」并填写这个注册码，即可注册老师账号，之后自行创建班级。修改后立即生效，旧注册码失效。</p>
        </div>
        <NTag :bordered="false" round :type="inv.saved.enabled ? 'success' : 'default'">{{ inv.saved.enabled ? '开放老师注册' : '未开放老师注册' }}</NTag>
      </div>
      <div class="ticket" :class="{ off: !inv.enabled }">
        <span class="lb">注册码</span>
        <NInput v-model:value="inv.code" class="in" placeholder="4~40 位字母、数字、- 或 _" :maxlength="40" :status="inv.code && !valid ? 'error' : undefined" />
        <NTooltip><template #trigger><NButton quaternary circle @click="gen"><template #icon><Dices :size="17" /></template></NButton></template>随机生成</NTooltip>
      </div>
      <div class="row">
        <label class="sw"><NSwitch v-model:value="inv.enabled" /> 开放老师注册</label>
        <span class="hint">{{ inv.source === 'env' ? '当前使用服务器 .env 中的 TEACHER_INVITE_CODE，在这里保存后以页面设置为准' : '由页面设置，优先于服务器 .env' }}</span>
        <NButton v-if="inv.saved.enabled" secondary @click="copy"><template #icon><Copy :size="15" /></template>复制给老师</NButton>
        <NButton type="primary" :loading="inv.saving" :disabled="!dirty || (inv.enabled && !valid)" @click="save">保存</NButton>
      </div>
    </section>

    <section class="card card-pad how">
      <h3 class="section-title"><GraduationCap :size="16" class="ti" /> 学生怎么注册？</h3>
      <ol>
        <li>老师登录后在「设置 → 班级管理」里新建班级，系统会为每个班级生成独立的<b>班级邀请码</b>；</li>
        <li>老师把邀请码发给学生，学生在登录页选择「注册 → 我是学生」并填写邀请码，就会进入对应班级；</li>
        <li>每个班级可以单独开关注册、更换邀请码；也可以下载模板批量导入学生名单，直接生成账号和初始密码。</li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.ti { vertical-align: -2px; margin-right: 2px; }
.ticket {
  display: flex; align-items: center; gap: 10px; margin-top: 10px; padding: 12px 14px 12px 18px; border-radius: 12px;
  border: 1.5px dashed color-mix(in srgb, var(--t-teal) 55%, var(--border)); background: linear-gradient(120deg, var(--t-teal-soft), transparent 65%);
}
.ticket.off { opacity: 0.6; }
.lb { font-size: 12.5px; font-weight: 650; color: var(--t-teal); white-space: nowrap; }
.in { flex: 1; }
.in :deep(input) { font-family: var(--mono); font-size: 15px; letter-spacing: 1px; }
.row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.sw { display: inline-flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 550; }
.hint { flex: 1; min-width: 200px; font-size: 12px; color: var(--text-3); }
.how { margin-top: 14px; }
.how ol { margin: 8px 0 0; padding-left: 20px; font-size: 13.5px; line-height: 1.9; color: var(--text-2); }
</style>
