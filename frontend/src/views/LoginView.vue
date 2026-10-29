<script setup lang="ts">
// 登录 / 注册。左侧品牌介绍，右侧表单；窄屏只保留表单
import {
  Check, ChartLine, CircleAlert, GraduationCap, IdCard, Lock, MessageSquareText, Moon, Sun, Ticket, User,
} from 'lucide-vue-next'
import { NButton, NCheckbox, NInput } from 'naive-ui'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/stores/auth'
import { useTheme } from '@/stores/theme'

const auth = useAuth()
const theme = useTheme()
const route = useRoute()
const router = useRouter()

const mode = ref<'login' | 'register'>(route.query.mode === 'register' && auth.registration ? 'register' : 'login')
const loading = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '', confirm: '', invite: '', displayName: '', remember: true })

watch(mode, () => {
  error.value = ''
  form.password = ''
  form.confirm = ''
})

const rules = computed(() => [
  { ok: form.password.length >= 8 && form.password.length <= 64, text: '8 位以上' },
  { ok: /[A-Za-z]/.test(form.password) && /\d/.test(form.password), text: '同时包含字母和数字' },
])
const usernameOk = computed(() => /^[A-Za-z0-9_一-龥]{2,20}$/.test(form.username.trim()))

function validate(): string {
  if (!form.username.trim()) return '请输入用户名'
  if (!form.password) return '请输入密码'
  if (mode.value === 'login') return ''
  if (!usernameOk.value) return '用户名为 2~20 位中文、字母、数字或下划线'
  if (!rules.value.every((r) => r.ok)) return '密码需要 8 位以上，并同时包含字母和数字'
  if (form.password !== form.confirm) return '两次输入的密码不一致'
  if (!form.invite.trim()) return '请输入老师提供的邀请码'
  return ''
}

async function submit() {
  error.value = validate()
  if (error.value) return
  loading.value = true
  try {
    if (mode.value === 'login') await auth.login(form.username.trim(), form.password, form.remember)
    else await auth.register(form.username.trim(), form.password, form.invite.trim(), form.displayName.trim())
    const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
    await router.replace(target)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const features = [
  { icon: MessageSquareText, title: '对话即操作', text: '一句话调取策略、修改参数、执行回测' },
  { icon: ChartLine, title: '严谨的回测', text: '次日开盘成交、真实交易成本，杜绝未来函数' },
  { icon: GraduationCap, title: '讲清楚原理', text: '智能解读报告，每条优化建议都附带原理' },
]
</script>

<template>
  <div class="auth">
    <section class="hero" aria-hidden="true">
      <div class="glow g1" />
      <div class="glow g2" />
      <div class="hero-top">
        <img src="/logo.svg" alt="" width="34" height="34" class="logo" />
        <span>量化策略教学平台</span>
      </div>

      <div class="hero-body">
        <h1>用对话学量化</h1>
        <p class="lead">22 种经典股票与期货策略，修改参数、回测历史行情，让智能助手讲清楚每一个指标背后的道理。</p>
        <ul class="features">
          <li v-for="f in features" :key="f.title">
            <span class="f-icon"><component :is="f.icon" :size="18" :stroke-width="1.9" /></span>
            <span><b>{{ f.title }}</b><em>{{ f.text }}</em></span>
          </li>
        </ul>
      </div>

      <div class="chart-card">
        <div class="chart-head">
          <span><i class="dot main" />策略净值</span>
          <span><i class="dot bench" />沪深 300</span>
        </div>
        <svg viewBox="0 0 320 120" preserveAspectRatio="none" class="chart">
          <defs>
            <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#fff" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#fff" stop-opacity="0" />
            </linearGradient>
          </defs>
          <g class="grid"><line x1="0" y1="30" x2="320" y2="30" /><line x1="0" y1="60" x2="320" y2="60" /><line x1="0" y1="90" x2="320" y2="90" /></g>
          <path class="area" d="M0,100 C30,96 45,84 70,88 S110,64 135,68 S175,48 200,54 S245,28 270,34 S305,16 320,12 L320,120 L0,120 Z" />
          <path class="bench" d="M0,102 C40,99 70,104 100,98 S160,92 190,95 S250,86 280,88 S310,82 320,80" />
          <path class="line" d="M0,100 C30,96 45,84 70,88 S110,64 135,68 S175,48 200,54 S245,28 270,34 S305,16 320,12" />
        </svg>
        <div class="chips"><span>年化收益</span><span>最大回撤</span><span>夏普比率</span><span>胜率</span></div>
      </div>

      <div class="hero-foot">教学实验工具 · 回测结果仅用于学习，不构成任何投资建议</div>
    </section>

    <section class="panel">
      <button class="theme-btn" :aria-label="theme.isDark ? '切换到浅色' : '切换到深色'" @click="theme.toggle()">
        <Sun v-if="theme.isDark" :size="17" />
        <Moon v-else :size="17" />
      </button>

      <div class="form-wrap">
        <div class="mobile-brand">
          <img src="/logo.svg" alt="" width="40" height="40" />
          <span>量化策略教学平台</span>
        </div>

        <h2>{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</h2>
        <p class="sub">{{ mode === 'login' ? '登录后继续你的量化实验' : '使用老师提供的邀请码注册' }}</p>

        <div v-if="auth.registration" class="seg" role="tablist">
          <span class="seg-ind" :class="{ right: mode === 'register' }" />
          <button type="button" role="tab" :aria-selected="mode === 'login'" :class="{ on: mode === 'login' }" @click="mode = 'login'">登录</button>
          <button type="button" role="tab" :aria-selected="mode === 'register'" :class="{ on: mode === 'register' }" @click="mode = 'register'">注册</button>
        </div>

        <form class="form" novalidate @submit.prevent="submit">
          <label class="field">
            <span class="label">用户名</span>
            <NInput v-model:value="form.username" size="large" :maxlength="20" placeholder="请输入用户名" :input-props="{ autocomplete: 'username', name: 'username' }">
              <template #prefix><User :size="17" class="pi" /></template>
            </NInput>
          </label>

          <label v-if="mode === 'register'" class="field">
            <span class="label">显示名称 <i>选填，如真实姓名，方便老师辨认</i></span>
            <NInput v-model:value="form.displayName" size="large" :maxlength="20" placeholder="例如：张同学">
              <template #prefix><IdCard :size="17" class="pi" /></template>
            </NInput>
          </label>

          <label class="field">
            <span class="label">密码</span>
            <NInput
              v-model:value="form.password" type="password" size="large" show-password-on="click" :maxlength="64" placeholder="请输入密码"
              :input-props="{ autocomplete: mode === 'login' ? 'current-password' : 'new-password', name: 'password' }"
            >
              <template #prefix><Lock :size="17" class="pi" /></template>
            </NInput>
          </label>
          <div v-if="mode === 'register'" class="rules">
            <span v-for="r in rules" :key="r.text" :class="{ ok: r.ok }"><Check :size="13" :stroke-width="2.6" />{{ r.text }}</span>
          </div>

          <template v-if="mode === 'register'">
            <label class="field">
              <span class="label">确认密码</span>
              <NInput
                v-model:value="form.confirm" type="password" size="large" show-password-on="click" :maxlength="64" placeholder="再输入一次密码"
                :status="form.confirm && form.confirm !== form.password ? 'error' : undefined" :input-props="{ autocomplete: 'new-password' }"
              >
                <template #prefix><Lock :size="17" class="pi" /></template>
              </NInput>
            </label>
            <label class="field">
              <span class="label">邀请码</span>
              <NInput v-model:value="form.invite" size="large" :maxlength="100" placeholder="向老师索取">
                <template #prefix><Ticket :size="17" class="pi" /></template>
              </NInput>
            </label>
          </template>

          <div v-if="mode === 'login'" class="row">
            <NCheckbox v-model:checked="form.remember">30 天内自动登录</NCheckbox>
            <span class="muted forgot">忘记密码请联系老师</span>
          </div>

          <transition name="err">
            <div v-if="error" class="error" role="alert"><CircleAlert :size="16" /><span>{{ error }}</span></div>
          </transition>

          <NButton attr-type="submit" type="primary" size="large" block :loading="loading" class="submit">
            {{ mode === 'login' ? '登 录' : '注册并登录' }}
          </NButton>
        </form>

        <p v-if="!auth.registration" class="foot-hint">还没有账号？请向老师索取账号或邀请码。</p>
        <p v-else-if="mode === 'login'" class="foot-hint">还没有账号？<a href="#" @click.prevent="mode = 'register'">用邀请码注册</a></p>
        <p v-else class="foot-hint">已有账号？<a href="#" @click.prevent="mode = 'login'">直接登录</a></p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  background: var(--bg);
}

/* ---------------- 左侧品牌区 ---------------- */
.hero {
  --h1: #1c5cab;
  --h2: #2a78d6;
  --h3: #4a95ea;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 40px 56px;
  color: #fff;
  background:
    linear-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(150deg, var(--h1) 0%, var(--h2) 55%, var(--h3) 100%);
}
:root[data-theme='dark'] .hero { --h1: #0b2547; --h2: #134a8c; --h3: #1f63b5; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme='light']) .hero { --h1: #0b2547; --h2: #134a8c; --h3: #1f63b5; }
}
.glow { position: absolute; border-radius: 50%; filter: blur(60px); pointer-events: none; }
.g1 { width: 380px; height: 380px; right: -120px; top: -100px; background: rgba(255, 255, 255, 0.16); }
.g2 { width: 300px; height: 300px; left: -100px; bottom: -80px; background: rgba(120, 190, 255, 0.22); }
.hero > *:not(.glow) { position: relative; }

.hero-top { display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 650; letter-spacing: 0.5px; }
.logo { border-radius: 9px; box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.35), 0 6px 18px rgba(0, 0, 0, 0.18); }

.hero-body { margin-top: auto; padding-top: 48px; max-width: 470px; }
.hero h1 { margin: 0; font-size: 38px; line-height: 1.2; font-weight: 700; letter-spacing: 1px; }
.lead { margin: 14px 0 0; font-size: 15px; line-height: 1.75; color: rgba(255, 255, 255, 0.82); }
.features { list-style: none; margin: 28px 0 0; padding: 0; display: flex; flex-direction: column; gap: 16px; }
.features li { display: flex; align-items: center; gap: 14px; }
.f-icon {
  width: 38px; height: 38px; flex-shrink: 0; display: grid; place-items: center; border-radius: 11px;
  background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.22);
}
.features b { display: block; font-size: 14.5px; font-weight: 600; }
.features em { display: block; font-style: normal; font-size: 13px; color: rgba(255, 255, 255, 0.72); margin-top: 1px; }

.chart-card {
  margin-top: 36px; max-width: 470px; padding: 16px 18px 14px; border-radius: 16px;
  background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(6px); box-shadow: 0 18px 40px rgba(6, 30, 70, 0.25);
}
.chart-head { display: flex; gap: 18px; font-size: 12px; color: rgba(255, 255, 255, 0.85); }
.chart-head span { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.dot.main { background: #fff; }
.dot.bench { background: rgba(255, 255, 255, 0.5); }
.chart { width: 100%; height: 120px; margin-top: 8px; display: block; overflow: visible; }
.grid line { stroke: rgba(255, 255, 255, 0.12); stroke-width: 1; }
.area { fill: url(#area); opacity: 0; animation: fade-in 1s ease 0.9s forwards; }
.bench { fill: none; stroke: rgba(255, 255, 255, 0.5); stroke-width: 1.6; stroke-dasharray: 4 4; }
.line {
  fill: none; stroke: #fff; stroke-width: 2.4; stroke-linecap: round;
  stroke-dasharray: 520; stroke-dashoffset: 520; animation: draw 1.6s cubic-bezier(0.4, 0, 0.2, 1) 0.2s forwards;
}
.bench, .line, .grid line { vector-effect: non-scaling-stroke; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.chips span { font-size: 11.5px; padding: 3px 10px; border-radius: 999px; background: rgba(255, 255, 255, 0.14); color: rgba(255, 255, 255, 0.9); }
.hero-foot { margin-top: auto; padding-top: 32px; font-size: 12px; color: rgba(255, 255, 255, 0.62); }
@keyframes draw { to { stroke-dashoffset: 0; } }
@keyframes fade-in { to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
  .line, .area { animation: none; stroke-dashoffset: 0; opacity: 1; }
}

/* ---------------- 右侧表单 ---------------- */
.panel {
  position: relative; display: flex; align-items: center; justify-content: center; padding: 48px 24px;
  background:
    radial-gradient(520px 320px at 100% 0%, var(--primary-soft), transparent 70%),
    radial-gradient(420px 280px at 0% 100%, var(--primary-soft), transparent 70%);
}
.theme-btn {
  position: absolute; top: 20px; right: 20px; width: 38px; height: 38px; border-radius: 10px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text-2); cursor: pointer;
  display: grid; place-items: center; transition: background 0.15s, color 0.15s;
}
.theme-btn:hover { background: var(--surface-3); color: var(--text-1); }
.form-wrap { width: 100%; max-width: 380px; }
.mobile-brand { display: none; }
h2 { margin: 0; font-size: 28px; font-weight: 700; color: var(--text-1); letter-spacing: 0.5px; }
.sub { margin: 8px 0 0; color: var(--text-3); font-size: 14px; }

.seg {
  position: relative; display: grid; grid-template-columns: 1fr 1fr; margin-top: 26px; padding: 4px;
  border-radius: 12px; background: var(--surface-3);
}
.seg button {
  position: relative; z-index: 1; height: 36px; border: 0; background: none; cursor: pointer;
  font: inherit; font-size: 14px; color: var(--text-3); border-radius: 9px; transition: color 0.2s;
}
.seg button.on { color: var(--text-1); font-weight: 600; }
.seg-ind {
  position: absolute; top: 4px; left: 4px; width: calc(50% - 4px); height: 36px; border-radius: 9px;
  background: var(--surface); box-shadow: var(--shadow-sm); transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.seg-ind.right { transform: translateX(100%); }

.form { margin-top: 24px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 7px; }
.label { font-size: 13px; font-weight: 500; color: var(--text-2); }
.label i { font-style: normal; font-weight: 400; color: var(--text-3); margin-left: 4px; font-size: 12px; }
.pi { color: var(--text-3); }
.rules { display: flex; gap: 14px; margin-top: -8px; font-size: 12px; color: var(--text-3); }
.rules span { display: inline-flex; align-items: center; gap: 4px; transition: color 0.2s; }
.rules span svg { opacity: 0.35; transition: opacity 0.2s; }
.rules span.ok { color: var(--down); }
.rules span.ok svg { opacity: 1; }
.row { display: flex; align-items: center; justify-content: space-between; margin-top: -2px; }
.forgot { font-size: 12.5px; }
.error {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 10px; font-size: 13px;
  color: var(--up); background: var(--up-soft);
}
.error svg { flex-shrink: 0; }
.err-enter-active, .err-leave-active { transition: opacity 0.2s, transform 0.2s; }
.err-enter-from, .err-leave-to { opacity: 0; transform: translateY(-4px); }
.submit { margin-top: 4px; height: 46px; font-size: 15px; border-radius: 11px; }
.foot-hint { margin: 22px 0 0; text-align: center; font-size: 13px; color: var(--text-3); }
.foot-hint a { color: var(--primary); font-weight: 500; }
.foot-hint a:hover { text-decoration: underline; }

@media (max-width: 960px) {
  .auth { grid-template-columns: minmax(0, 1fr); }
  .hero { display: none; }
  .panel {
    align-items: flex-start; padding: 72px 16px 40px;
    background: radial-gradient(1200px 380px at 50% -160px, var(--primary-soft), transparent 70%);
  }
  .mobile-brand {
    display: flex; align-items: center; gap: 12px; margin-bottom: 28px;
    font-size: 17px; font-weight: 650; color: var(--text-1);
  }
  .mobile-brand img { border-radius: 10px; box-shadow: var(--shadow-md); }
}
</style>
