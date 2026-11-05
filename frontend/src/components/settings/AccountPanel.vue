<script setup lang="ts">
// 个人账号：查看身份和所属班级，修改显示名称与密码
import { KeyRound, School, UserRound } from 'lucide-vue-next'
import { NButton, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import { reactive, ref, watch } from 'vue'
import { api } from '@/api/client'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
const toast = useMessage()
const name = ref(auth.user?.display_name ?? '')
watch(() => auth.user?.display_name, (v) => { name.value = v ?? '' })
const savingName = ref(false)
const pwd = reactive({ old: '', new: '', confirm: '', saving: false })

async function saveName() {
  savingName.value = true
  try { await auth.updateProfile(name.value.trim()); toast.success('已保存') } catch (e: any) { toast.error(e.message) } finally { savingName.value = false }
}
async function savePwd() {
  if (pwd.new !== pwd.confirm) return toast.error('两次输入的新密码不一致')
  pwd.saving = true
  try {
    await api.post('/api/auth/password', { old: pwd.old, new: pwd.new })
    toast.success('密码已修改')
    Object.assign(pwd, { old: '', new: '', confirm: '' })
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    pwd.saving = false
  }
}
</script>

<template>
  <div class="panel-body">
    <section v-if="auth.user" class="card card-pad me">
      <span class="av" :class="auth.user.role">{{ (auth.user.display_name || auth.user.username).slice(0, 1) }}</span>
      <div class="me-t">
        <b>{{ auth.user.display_name }}</b>
        <em>用户名 {{ auth.user.username }} · {{ auth.user.role_label }}<template v-if="auth.user.class_name"> · {{ auth.user.class_name }}</template></em>
      </div>
      <span v-if="auth.user.class_name" class="cls"><School :size="14" /> {{ auth.user.class_name }}</span>
    </section>
    <section v-else class="card card-pad"><p class="muted">平台未开启账号登录，所有功能直接可用，无需个人账号设置。</p></section>

    <div v-if="auth.user" class="cols">
      <section class="card card-pad">
        <h3 class="section-title"><UserRound :size="16" class="ti" /> 显示名称</h3>
        <p class="section-sub">{{ auth.user.role === 'student' ? '老师在班级管理里看到的名字，建议填写真实姓名' : '学生和其他老师看到的名字' }}</p>
        <NForm label-placement="top" @submit.prevent="saveName">
          <NFormItem label="显示名称"><NInput v-model:value="name" :maxlength="20" /></NFormItem>
          <NButton type="primary" attr-type="submit" :loading="savingName" :disabled="!name.trim() || name === auth.user.display_name">保存</NButton>
        </NForm>
      </section>
      <section class="card card-pad">
        <h3 class="section-title"><KeyRound :size="16" class="ti" /> 修改密码</h3>
        <p class="section-sub">8~64 位，需要同时包含字母和数字。修改后其他设备需要重新登录</p>
        <NForm label-placement="top" @submit.prevent="savePwd">
          <NFormItem label="原密码"><NInput v-model:value="pwd.old" type="password" show-password-on="click" /></NFormItem>
          <NFormItem label="新密码"><NInput v-model:value="pwd.new" type="password" show-password-on="click" /></NFormItem>
          <NFormItem label="确认新密码"><NInput v-model:value="pwd.confirm" type="password" show-password-on="click" :status="pwd.confirm && pwd.confirm !== pwd.new ? 'error' : undefined" /></NFormItem>
          <NButton type="primary" attr-type="submit" :loading="pwd.saving" :disabled="!pwd.old || !pwd.new">修改密码</NButton>
        </NForm>
      </section>
    </div>
  </div>
</template>

<style scoped>
.me { display: flex; align-items: center; gap: 14px; background: linear-gradient(120deg, var(--surface) 40%, var(--primary-soft)); }
.av { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; font-size: 22px; font-weight: 700; color: var(--primary-ink); background: var(--primary-soft); }
.av.admin { color: #fff; background: var(--brand-grad); }
.av.teacher { color: var(--t-teal); background: var(--t-teal-soft); }
.me-t { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.me-t b { font-size: 18px; }
.me-t em { font-style: normal; font-size: 13px; color: var(--text-3); }
.cls { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px; border-radius: 999px; font-size: 13px; color: var(--t-violet); background: var(--t-violet-soft); }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.ti { vertical-align: -2px; margin-right: 2px; }
@media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }
</style>
