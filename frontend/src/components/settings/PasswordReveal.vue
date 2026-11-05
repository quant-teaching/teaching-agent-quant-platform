<script setup lang="ts">
// 显示新建账号 / 重置密码后的初始密码：只显示这一次，提示老师复制后发给学生
import { Copy, KeyRound } from 'lucide-vue-next'
import { NButton, NModal, useMessage } from 'naive-ui'
import { copyText } from '@/api/accounts'

const props = defineProps<{ username: string; password: string; title?: string }>()
const show = defineModel<boolean>('show', { default: false })
const toast = useMessage()

async function copy() {
  const ok = await copyText(`用户名：${props.username}\n密码：${props.password}\n登录网址：${location.origin}/login`)
  if (ok) toast.success('已复制用户名、密码和登录网址')
  else toast.info(`用户名：${props.username}  密码：${props.password}`)
}
</script>

<template>
  <NModal v-model:show="show" preset="card" :title="title || '账号密码'" :bordered="false" style="width: 420px; max-width: calc(100vw - 32px)">
    <div class="pr">
      <span class="pr-ic"><KeyRound :size="22" /></span>
      <div class="pr-grid">
        <span>用户名</span><b>{{ username }}</b>
        <span>密码</span><b class="pw">{{ password }}</b>
      </div>
      <p class="muted">密码只显示这一次，请复制后交给对方；对方登录后可以在「设置 → 个人账号」里修改密码。</p>
      <NButton type="primary" block @click="copy"><template #icon><Copy :size="15" /></template>复制账号信息</NButton>
    </div>
  </NModal>
</template>

<style scoped>
.pr { display: flex; flex-direction: column; align-items: center; gap: 14px; text-align: center; }
.pr-ic { width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; color: #fff; background: var(--brand-grad); }
.pr-grid { display: grid; grid-template-columns: auto 1fr; gap: 8px 16px; width: 100%; padding: 14px 18px; border-radius: 12px; text-align: left;
  background: var(--surface-2); border: 1px dashed var(--border-strong); }
.pr-grid span { color: var(--text-3); font-size: 13px; }
.pr-grid b { font-family: var(--mono); font-size: 15px; }
.pw { letter-spacing: 1px; color: var(--primary-ink); }
.pr p { margin: 0; font-size: 12.5px; }
</style>
