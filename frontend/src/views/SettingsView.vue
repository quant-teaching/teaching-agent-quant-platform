<script setup lang="ts">
import { ArrowDown, ArrowUp, CircleCheck, CircleX, KeyRound, Link2, Loader2, LockKeyhole, Pencil, Plus, RefreshCw, Search, Server, Trash2, Users, X, Zap } from 'lucide-vue-next'
import {
  NButton, NCheckbox, NDataTable, NEmpty, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, NSelect, NSlider, NSwitch, NTag, NTooltip, useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { computed, h, onMounted, reactive, ref } from 'vue'
import { ADMIN_PW_KEY, api, type ModelRef, type Provider, type Routing } from '@/api/client'
import { useAuth, type AuthUser } from '@/stores/auth'
import { timeAgo } from '@/utils/format'

const toast = useMessage()
const providers = ref<Provider[]>([])
const routing = ref<Routing>({ primary: null, fallbacks: [], temperature: 0.3, timeout: 90, first_token_timeout: 45 })
const routingDirty = ref(false)
const tests = reactive<Record<string, { loading?: boolean; ok?: boolean; latency_ms?: number; tool_calling?: boolean; error?: string }>>({})

async function load() {
  const [ps, r, lk] = await Promise.all([
    api.get<Provider[]>('/api/llm/providers'), api.get<Routing>('/api/llm/routing'),
    api.get<{ locked: boolean; mode: 'role' | 'password' }>('/api/llm/lock'),
  ])
  providers.value = ps
  routing.value = r
  routingDirty.value = false
  lock.mode = lk.mode
  lock.locked = lk.locked && !(lk.mode === 'password' && storedAdminPw())
  if (auth.enabled && auth.user?.role === 'admin') loadUsers()
}

// ---------------------------------------------------------------- 只读 / 解锁

const auth = useAuth()
const lock = reactive({ locked: false, mode: 'password' as 'role' | 'password', pw: '', checking: false })
function storedAdminPw() {
  try {
    return sessionStorage.getItem(ADMIN_PW_KEY)
  } catch {
    return null
  }
}
async function unlock() {
  lock.checking = true
  try {
    await api.post('/api/llm/unlock', { password: lock.pw })
    try {
      sessionStorage.setItem(ADMIN_PW_KEY, lock.pw)
    } catch { /* 隐私模式：只在本次操作中有效 */ }
    lock.locked = false
    lock.pw = ''
    toast.success('已解锁，本次浏览器会话内可以修改模型设置')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    lock.checking = false
  }
}

// ---------------------------------------------------------------- 用户管理（管理员）

const users = ref<AuthUser[]>([])
async function loadUsers() {
  users.value = await api.get<AuthUser[]>('/api/auth/users')
}
async function setDisabled(u: AuthUser, disabled: boolean) {
  try {
    const nu = await api.patch<AuthUser>(`/api/auth/users/${u.id}`, { disabled })
    Object.assign(u, nu)
    toast.success(disabled ? `已停用「${u.display_name}」，对方会立即退出登录` : `已启用「${u.display_name}」`)
  } catch (e: any) {
    toast.error(e.message)
  }
}
async function removeUser(u: AuthUser) {
  try {
    await api.del(`/api/auth/users/${u.id}`)
    users.value = users.value.filter((x) => x.id !== u.id)
  } catch (e: any) {
    toast.error(e.message)
  }
}
const userCols = computed<DataTableColumns<AuthUser>>(() => [
  {
    title: '用户', key: 'username', minWidth: 160,
    render: (u) => h('div', { class: 'u-cell' }, [
      h('span', { class: ['u-av', u.role === 'admin' ? 'admin' : ''] }, (u.display_name || u.username).slice(0, 1).toUpperCase()),
      h('span', [h('b', u.display_name), h('em', u.username)]),
    ]),
  },
  { title: '角色', key: 'role', width: 90, render: (u) => h(NTag, { size: 'small', bordered: false, type: u.role === 'admin' ? 'info' : 'default' }, () => (u.role === 'admin' ? '管理员' : '学生')) },
  { title: '注册时间', key: 'created_at', width: 120, render: (u) => u.created_at.slice(0, 10) },
  { title: '最近登录', key: 'last_login', width: 110, render: (u) => (u.last_login ? timeAgo(u.last_login) : '—') },
  {
    title: '启用', key: 'disabled', width: 70,
    render: (u) => (u.id === auth.user?.id ? '—' : h(NSwitch, { size: 'small', value: !u.disabled, 'onUpdate:value': (v: boolean) => setDisabled(u, !v) })),
  },
  {
    title: '', key: 'ops', width: 70, align: 'right',
    render: (u) => (u.id === auth.user?.id ? null : h(NPopconfirm, { onPositiveClick: () => removeUser(u) }, {
      trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, () => '删除'),
      default: () => `删除「${u.display_name}」？他的对话和回测记录会保留，但无法再登录`,
    })),
  },
])

// ---------------------------------------------------------------- 接口编辑弹窗

const TEMPLATES = [
  { name: 'OpenAI', url: 'https://api.openai.com/v1' },
  { name: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { name: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { name: '硅基流动', url: 'https://api.siliconflow.cn/v1' },
  { name: 'Moonshot', url: 'https://api.moonshot.cn/v1' },
  { name: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4' },
]

const modal = reactive({
  show: false, editingId: null as number | null, name: '', base_url: '', api_key: '', hasKey: false,
  selected: [] as string[], fetched: [] as string[], fetching: false, filter: '', manual: '', saving: false, fetchError: '',
})

function openAdd() {
  Object.assign(modal, { show: true, editingId: null, name: '', base_url: '', api_key: '', hasKey: false, selected: [], fetched: [], filter: '', manual: '', fetchError: '' })
}
function openEdit(p: Provider) {
  Object.assign(modal, { show: true, editingId: p.id, name: p.name, base_url: p.base_url, api_key: '', hasKey: p.has_key, selected: [...p.models], fetched: [...p.models], filter: '', manual: '', fetchError: '' })
}
function useTemplate(t: (typeof TEMPLATES)[number]) {
  modal.base_url = t.url
  if (!modal.name || TEMPLATES.some((x) => x.name === modal.name)) modal.name = t.name
}

async function fetchModels() {
  if (!modal.base_url.trim()) return toast.warning('请先填写 API 地址')
  if (!modal.api_key && !modal.hasKey) return toast.warning('请先填写 API Key')
  modal.fetching = true
  modal.fetchError = ''
  try {
    const r = await api.post<{ base_url: string; models: string[] }>('/api/llm/models/fetch', {
      base_url: modal.base_url, api_key: modal.api_key || null, provider_id: modal.editingId,
    })
    modal.base_url = r.base_url
    modal.fetched = [...new Set([...r.models, ...modal.selected])].sort()
    if (!modal.selected.length && r.models.length <= 8) modal.selected = [...r.models]
    toast.success(`获取到 ${r.models.length} 个模型`)
  } catch (e: any) {
    modal.fetchError = e.message
  } finally {
    modal.fetching = false
  }
}

const filtered = computed(() => {
  const f = modal.filter.trim().toLowerCase()
  return f ? modal.fetched.filter((m) => m.toLowerCase().includes(f)) : modal.fetched
})
function toggleModel(m: string, on: boolean) {
  modal.selected = on ? [...new Set([...modal.selected, m])] : modal.selected.filter((x) => x !== m)
}
function selectAllFiltered(on: boolean) {
  const set = new Set(modal.selected)
  for (const m of filtered.value) on ? set.add(m) : set.delete(m)
  modal.selected = [...set]
}
function addManual() {
  const names = modal.manual.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean)
  if (!names.length) return
  modal.fetched = [...new Set([...modal.fetched, ...names])].sort()
  modal.selected = [...new Set([...modal.selected, ...names])]
  modal.manual = ''
}

async function saveProvider() {
  if (!modal.name.trim() || !modal.base_url.trim()) return toast.warning('名称和 API 地址不能为空')
  if (!modal.selected.length) return toast.warning('至少选择或手动添加一个模型')
  modal.saving = true
  const body = { name: modal.name.trim(), base_url: modal.base_url.trim(), api_key: modal.api_key || null, models: modal.selected }
  try {
    if (modal.editingId) await api.put(`/api/llm/providers/${modal.editingId}`, body)
    else {
      const p = await api.post<Provider>('/api/llm/providers', body)
      if (!routing.value.primary) {
        routing.value.primary = { provider_id: p.id, model: modal.selected[0] }
        await api.put('/api/llm/routing', routing.value)
        toast.info(`已把 ${modal.selected[0]} 设为主模型`)
      }
    }
    modal.show = false
    toast.success('已保存')
    await load()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    modal.saving = false
  }
}

async function removeProvider(p: Provider) {
  await api.del(`/api/llm/providers/${p.id}`)
  toast.success(`已删除「${p.name}」`)
  load()
}
async function toggleEnabled(p: Provider, v: boolean) {
  await api.put(`/api/llm/providers/${p.id}`, { enabled: v })
  p.enabled = v
}
async function refresh(p: Provider) {
  try {
    const np = await api.post<Provider>(`/api/llm/providers/${p.id}/refresh-models`)
    const added = np.models.filter((m) => !p.models.includes(m))
    Object.assign(p, np)
    toast.success(added.length ? `新增 ${added.length} 个模型` : '模型列表已是最新')
  } catch (e: any) {
    toast.error(e.message)
  }
}

// ---------------------------------------------------------------- 调用顺序

const modelOptions = computed(() =>
  providers.value.filter((p) => p.enabled).map((p) => ({
    type: 'group', label: p.name, key: p.id,
    children: p.models.map((m) => ({ label: m, value: `${p.id}::${m}` })),
  })),
)
const toKey = (r: ModelRef | null) => (r ? `${r.provider_id}::${r.model}` : null)
const fromKey = (k: string): ModelRef => {
  const [pid, ...rest] = k.split('::')
  return { provider_id: Number(pid), model: rest.join('::') }
}
const providerName = (id: number) => providers.value.find((p) => p.id === id)?.name ?? '已删除的接口'

const primaryKey = computed({
  get: () => toKey(routing.value.primary),
  set: (k) => { routing.value.primary = k ? fromKey(k) : null; routingDirty.value = true },
})
const addFallback = ref<string | null>(null)
function pushFallback(k: string | null) {
  if (!k) return
  const ref_ = fromKey(k)
  if (toKey(routing.value.primary) === k || routing.value.fallbacks.some((f) => toKey(f) === k)) {
    toast.warning('这个模型已经在列表里了')
  } else {
    routing.value.fallbacks.push(ref_)
    routingDirty.value = true
  }
  addFallback.value = null
}
function moveFallback(i: number, d: number) {
  const f = routing.value.fallbacks
  const j = i + d
  if (j < 0 || j >= f.length) return
  ;[f[i], f[j]] = [f[j], f[i]]
  routingDirty.value = true
}
function removeFallback(i: number) {
  routing.value.fallbacks.splice(i, 1)
  routingDirty.value = true
}
async function saveRouting() {
  try {
    routing.value = await api.put<Routing>('/api/llm/routing', routing.value)
    routingDirty.value = false
    toast.success('调用顺序已保存，下一条消息开始生效')
  } catch (e: any) {
    toast.error(e.message)
  }
}

async function test(ref_: ModelRef) {
  const k = toKey(ref_)!
  tests[k] = { loading: true }
  try {
    tests[k] = await api.post('/api/llm/test', ref_)
  } catch (e: any) {
    tests[k] = { ok: false, error: e.message }
  }
}

function roleOf(p: Provider, m: string) {
  if (routing.value.primary?.provider_id === p.id && routing.value.primary.model === m) return '主模型'
  const i = routing.value.fallbacks.findIndex((f) => f.provider_id === p.id && f.model === m)
  return i >= 0 ? `备用 ${i + 1}` : ''
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>模型设置</h1>
        <p>智能体通过 OpenAI 兼容接口调用大模型。可以接入多个服务商，并设置主模型失败时自动切换的备用模型。</p>
      </div>
    </div>

    <div v-if="lock.locked" class="lock-bar">
      <span class="lock-ic"><LockKeyhole :size="18" /></span>
      <div class="lock-text">
        <b>{{ lock.mode === 'role' ? '只有管理员可以修改模型设置' : '模型设置已锁定' }}</b>
        <span>{{ lock.mode === 'role' ? '你可以查看当前使用的模型；需要调整请联系老师。' : '输入管理员密码后才能添加、修改或测试模型接口。' }}</span>
      </div>
      <form v-if="lock.mode === 'password'" class="lock-form" @submit.prevent="unlock">
        <NInput v-model:value="lock.pw" type="password" show-password-on="click" placeholder="管理员密码" style="width: 180px" />
        <NButton type="primary" attr-type="submit" :loading="lock.checking" :disabled="!lock.pw">解锁</NButton>
      </form>
    </div>

    <!-- 调用顺序 -->
    <section class="card card-pad routing" :class="{ ro: lock.locked }">
      <div class="sec-head">
        <div>
          <h3 class="section-title">调用顺序</h3>
          <p class="section-sub">主模型请求失败、超时或返回空内容时，按顺序自动切换到下一个备用模型，并在对话中提示</p>
        </div>
        <NButton v-if="!lock.locked" type="primary" :disabled="!routingDirty" @click="saveRouting">保存调用顺序</NButton>
      </div>

      <div class="chain">
        <div class="chain-item primary">
          <span class="badge p">主模型</span>
          <NSelect v-model:value="primaryKey" :options="modelOptions as any" placeholder="选择主模型" filterable class="sel" />
          <template v-if="routing.primary">
            <NButton size="small" quaternary :loading="tests[toKey(routing.primary)!]?.loading" @click="test(routing.primary!)">
              <template #icon><Zap :size="14" /></template>测试
            </NButton>
            <span v-if="tests[toKey(routing.primary)!] && !tests[toKey(routing.primary)!].loading" class="test-res" :class="{ ok: tests[toKey(routing.primary)!].ok }">
              <template v-if="tests[toKey(routing.primary)!].ok"><CircleCheck :size="14" /> {{ tests[toKey(routing.primary)!].latency_ms }} ms · {{ tests[toKey(routing.primary)!].tool_calling ? '支持工具调用' : '未检测到工具调用' }}</template>
              <template v-else><CircleX :size="14" /> {{ tests[toKey(routing.primary)!].error }}</template>
            </span>
          </template>
        </div>

        <div v-for="(f, i) in routing.fallbacks" :key="toKey(f)!" class="chain-item">
          <span class="badge">备用 {{ i + 1 }}</span>
          <div class="fb-name"><b>{{ f.model }}</b><span class="muted">{{ providerName(f.provider_id) }}</span></div>
          <NButton size="small" quaternary :loading="tests[toKey(f)!]?.loading" @click="test(f)"><template #icon><Zap :size="14" /></template>测试</NButton>
          <span v-if="tests[toKey(f)!] && !tests[toKey(f)!].loading" class="test-res" :class="{ ok: tests[toKey(f)!].ok }">
            <template v-if="tests[toKey(f)!].ok"><CircleCheck :size="14" /> {{ tests[toKey(f)!].latency_ms }} ms · {{ tests[toKey(f)!].tool_calling ? '支持工具调用' : '未检测到工具调用' }}</template>
            <template v-else><CircleX :size="14" /> {{ tests[toKey(f)!].error }}</template>
          </span>
          <div class="ops">
            <button :disabled="i === 0" title="上移" @click="moveFallback(i, -1)"><ArrowUp :size="14" /></button>
            <button :disabled="i === routing.fallbacks.length - 1" title="下移" @click="moveFallback(i, 1)"><ArrowDown :size="14" /></button>
            <button title="移除" @click="removeFallback(i)"><X :size="14" /></button>
          </div>
        </div>

        <div v-if="!lock.locked" class="chain-item add">
          <Plus :size="15" class="muted" />
          <NSelect v-model:value="addFallback" :options="modelOptions as any" placeholder="添加备用模型" filterable class="sel" @update:value="pushFallback" />
        </div>
      </div>

      <div class="params">
        <div class="param">
          <span>温度 <NTooltip><template #trigger><span class="q">?</span></template>越低回答越稳定、越贴近工具数据，教学分析建议 0.2~0.5</NTooltip></span>
          <NSlider v-model:value="routing.temperature" :min="0" :max="1.2" :step="0.05" style="width: 180px" @update:value="routingDirty = true" />
          <b class="num">{{ routing.temperature.toFixed(2) }}</b>
        </div>
        <div class="param">
          <span>首字超时</span>
          <NInputNumber v-model:value="routing.first_token_timeout" :min="5" :max="300" size="small" style="width: 110px" @update:value="routingDirty = true"><template #suffix>秒</template></NInputNumber>
        </div>
        <div class="param">
          <span>请求超时</span>
          <NInputNumber v-model:value="routing.timeout" :min="5" :max="600" size="small" style="width: 110px" @update:value="routingDirty = true"><template #suffix>秒</template></NInputNumber>
        </div>
      </div>
    </section>

    <!-- 接口列表 -->
    <div class="sec-head list-head">
      <div>
        <h3 class="section-title">模型接口</h3>
        <p class="section-sub">支持 OpenAI、DeepSeek、通义千问、硅基流动、各类中转站等所有 OpenAI 兼容服务；API Key 只保存在本机后端，不会回传到页面</p>
      </div>
      <NButton v-if="!lock.locked" type="primary" @click="openAdd"><template #icon><Plus :size="16" /></template>添加接口</NButton>
    </div>

    <NEmpty v-if="!providers.length" description="还没有模型接口，点击右上角添加" class="card card-pad" />
    <div class="providers stagger" :class="{ ro: lock.locked }">
      <div v-for="p in providers" :key="p.id" class="card provider" :class="{ disabled: !p.enabled }">
        <div class="p-head">
          <div class="p-icon"><Server :size="17" /></div>
          <div class="p-title">
            <b>{{ p.name }}</b>
            <div class="p-meta"><Link2 :size="12" /> {{ p.base_url }}</div>
            <div class="p-meta"><KeyRound :size="12" /> {{ p.has_key ? p.api_key_masked : '未设置 Key' }}</div>
          </div>
          <NTooltip><template #trigger><NSwitch :value="p.enabled" size="small" @update:value="(v) => toggleEnabled(p, v)" /></template>{{ p.enabled ? '已启用' : '已停用（不会被调用）' }}</NTooltip>
        </div>
        <div class="models">
          <span v-for="m in p.models" :key="m" class="mchip" :class="{ used: roleOf(p, m) }">
            {{ m }}<em v-if="roleOf(p, m)">{{ roleOf(p, m) }}</em>
            <button class="mtest" title="测试这个模型" @click="test({ provider_id: p.id, model: m })">
              <Loader2 v-if="tests[`${p.id}::${m}`]?.loading" :size="12" class="spin" />
              <CircleCheck v-else-if="tests[`${p.id}::${m}`]?.ok" :size="12" class="ok" />
              <CircleX v-else-if="tests[`${p.id}::${m}`] && !tests[`${p.id}::${m}`].ok" :size="12" class="bad" />
              <Zap v-else :size="12" />
            </button>
          </span>
        </div>
        <div v-if="!lock.locked" class="p-ops">
          <NButton size="small" quaternary @click="refresh(p)"><template #icon><RefreshCw :size="14" /></template>刷新模型列表</NButton>
          <NButton size="small" quaternary @click="openEdit(p)"><template #icon><Pencil :size="14" /></template>编辑</NButton>
          <NPopconfirm @positive-click="removeProvider(p)">
            <template #trigger><NButton size="small" quaternary type="error"><template #icon><Trash2 :size="14" /></template>删除</NButton></template>
            删除「{{ p.name }}」？使用它的主模型 / 备用模型也会被移除
          </NPopconfirm>
        </div>
      </div>
    </div>

    <!-- 用户管理 -->
    <section v-if="auth.enabled && auth.user?.role === 'admin'" class="card card-pad users">
      <div class="sec-head">
        <div>
          <h3 class="section-title"><Users :size="16" class="ti" /> 用户管理</h3>
          <p class="section-sub">
            {{ auth.registration ? '学生用你提供的邀请码自行注册（邀请码在服务器 .env 的 INVITE_CODE 中设置）' : '当前未开放注册：在服务器 .env 中设置 INVITE_CODE 后，学生可以用邀请码注册' }}；
            停用账号会让对方立即退出登录
          </p>
        </div>
        <NTag :bordered="false" round>{{ users.length }} 个账号</NTag>
      </div>
      <NDataTable :columns="userCols" :data="users" size="small" :bordered="false" :scroll-x="640" :pagination="{ pageSize: 10 }" />
    </section>

    <!-- 添加 / 编辑接口 -->
    <NModal v-model:show="modal.show" preset="card" :title="modal.editingId ? '编辑模型接口' : '添加模型接口'" style="width: 640px; max-width: calc(100vw - 32px)" :bordered="false">
      <NForm label-placement="top" :show-feedback="false" class="mform">
        <NFormItem v-if="!modal.editingId" label="快速填写">
          <div class="tpls">
            <button v-for="t in TEMPLATES" :key="t.name" class="tpl" :class="{ on: modal.base_url === t.url }" @click.prevent="useTemplate(t)">{{ t.name }}</button>
          </div>
        </NFormItem>
        <NFormItem label="名称"><NInput v-model:value="modal.name" placeholder="便于识别，如：DeepSeek 官方、学校中转站" /></NFormItem>
        <NFormItem label="API 地址">
          <NInput v-model:value="modal.base_url" placeholder="https://api.example.com/v1（没写 /v1 也可以，获取模型时会自动识别）" />
        </NFormItem>
        <NFormItem label="API Key">
          <NInput v-model:value="modal.api_key" type="password" show-password-on="click" :placeholder="modal.hasKey ? '已保存，留空表示不修改' : 'sk-...'" />
        </NFormItem>
        <NFormItem>
          <template #label>
            <div class="mlabel">
              <span>模型 <span class="muted">已选 {{ modal.selected.length }} 个</span></span>
              <NButton size="small" secondary type="primary" :loading="modal.fetching" @click="fetchModels"><template #icon><RefreshCw :size="14" /></template>获取模型列表</NButton>
            </div>
          </template>
          <div class="mbox">
            <div v-if="modal.fetchError" class="ferr"><CircleX :size="14" /> {{ modal.fetchError }}</div>
            <template v-if="modal.fetched.length">
              <div class="mtools">
                <NInput v-model:value="modal.filter" size="small" placeholder="搜索模型" clearable><template #prefix><Search :size="14" /></template></NInput>
                <NButton size="small" quaternary @click="selectAllFiltered(true)">全选</NButton>
                <NButton size="small" quaternary @click="selectAllFiltered(false)">清空</NButton>
              </div>
              <div class="mlist">
                <NCheckbox v-for="m in filtered" :key="m" :checked="modal.selected.includes(m)" @update:checked="(v) => toggleModel(m, v)">{{ m }}</NCheckbox>
              </div>
            </template>
            <div v-else-if="!modal.fetchError" class="muted hint">填写地址和 Key 后点击「获取模型列表」；接口不支持列表时，也可以在下方手动填写模型名</div>
            <div class="manual">
              <NInput v-model:value="modal.manual" size="small" placeholder="手动添加模型名，多个用逗号分隔，回车确认" @keydown.enter.prevent="addManual" />
              <NButton size="small" @click="addManual">添加</NButton>
            </div>
            <div v-if="modal.selected.length" class="sel-tags">
              <NTag v-for="m in modal.selected" :key="m" size="small" closable round @close="toggleModel(m, false)">{{ m }}</NTag>
            </div>
          </div>
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="mfoot">
          <NButton @click="modal.show = false">取消</NButton>
          <NButton type="primary" :loading="modal.saving" @click="saveProvider">保存</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.lock-bar {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; padding: 14px 16px;
  border-radius: 12px; background: var(--warn-soft); border: 1px solid color-mix(in srgb, var(--warn) 25%, transparent);
}
.lock-ic { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; color: var(--warn); background: var(--surface); flex-shrink: 0; }
.lock-text { flex: 1; min-width: 200px; display: flex; flex-direction: column; gap: 2px; font-size: 13px; color: var(--text-2); }
.lock-text b { font-size: 14px; color: var(--text-1); }
.lock-form { display: flex; gap: 8px; }
.ro { pointer-events: none; }
.ro :deep(.n-base-selection), .ro :deep(.n-slider), .ro :deep(.n-input-number), .ro :deep(.n-switch), .ro :deep(.ops), .ro :deep(.mtest), .ro :deep(.n-button) { opacity: 0.5; }
.users { margin-top: 18px; }
.ti { vertical-align: -2px; margin-right: 2px; }
:deep(.u-cell) { display: flex; align-items: center; gap: 10px; }
:deep(.u-cell b) { display: block; font-weight: 600; font-size: 13px; }
:deep(.u-cell em) { display: block; font-style: normal; font-size: 12px; color: var(--text-3); }
:deep(.u-av) {
  width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; flex-shrink: 0;
  font-size: 13px; font-weight: 650; color: var(--primary-ink); background: var(--primary-soft);
}
:deep(.u-av.admin) { color: #fff; background: var(--primary); }
.page { max-width: 1080px; }
.sec-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.list-head { margin: 28px 0 12px; }
.chain { display: flex; flex-direction: column; gap: 8px; margin: 6px 0 16px; }
.chain-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); flex-wrap: wrap; }
.chain-item.primary { border-color: var(--primary); background: var(--primary-soft); }
.chain-item.add { border-style: dashed; background: transparent; }
.badge { font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 6px; background: var(--surface-3); color: var(--text-2); white-space: nowrap; }
.badge.p { background: var(--primary); color: #fff; }
.sel { width: 320px; max-width: 100%; }
.fb-name { display: flex; flex-direction: column; min-width: 200px; line-height: 1.35; }
.fb-name b { font-weight: 600; font-size: 13.5px; }
.fb-name span { font-size: 12px; }
.test-res { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--up); }
.test-res.ok { color: var(--down); }
.ops { margin-left: auto; display: flex; gap: 2px; }
.ops button { border: none; background: none; cursor: pointer; color: var(--text-2); padding: 5px; border-radius: 6px; display: grid; }
.ops button:hover:not(:disabled) { background: var(--surface-3); color: var(--text-1); }
.ops button:disabled { opacity: 0.3; cursor: default; }
.params { display: flex; gap: 28px; flex-wrap: wrap; padding-top: 12px; border-top: 1px solid var(--border); }
.param { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-2); }
.q { display: inline-grid; place-items: center; width: 15px; height: 15px; font-size: 10px; border-radius: 50%; background: var(--surface-3); color: var(--text-3); cursor: help; }
.providers { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 14px; }
.provider { padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; transition: opacity 0.2s; }
.provider.disabled { opacity: 0.6; }
.p-head { display: flex; gap: 12px; align-items: flex-start; }
.p-icon { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: var(--primary-soft); color: var(--primary); flex-shrink: 0; }
.p-title { flex: 1; min-width: 0; }
.p-title b { font-size: 14.5px; }
.p-meta { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono); }
.models { display: flex; flex-wrap: wrap; gap: 6px; }
.mchip { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; padding: 3px 4px 3px 10px; border-radius: 999px; background: var(--surface-3); color: var(--text-1); font-family: var(--mono); }
.mchip.used { background: var(--primary-soft); color: var(--primary-ink); }
.mchip em { font-style: normal; font-family: var(--font); font-size: 11px; font-weight: 600; }
.mtest { border: none; background: var(--surface); color: var(--text-3); width: 20px; height: 20px; border-radius: 50%; cursor: pointer; display: grid; place-items: center; }
.mtest:hover { color: var(--primary); }
.mtest .ok { color: var(--down); }
.mtest .bad { color: var(--up); }
.p-ops { display: flex; gap: 4px; border-top: 1px solid var(--border); padding-top: 8px; margin-top: auto; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.mform { display: flex; flex-direction: column; gap: 14px; }
.tpls { display: flex; flex-wrap: wrap; gap: 6px; }
.tpl { border: 1px solid var(--border); background: var(--surface); color: var(--text-2); padding: 4px 12px; border-radius: 999px; cursor: pointer; font-size: 12.5px; font-family: inherit; }
.tpl:hover { border-color: var(--primary); color: var(--primary); }
.tpl.on { background: var(--primary-soft); border-color: var(--primary); color: var(--primary-ink); }
.mlabel { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.mbox { width: 100%; border: 1px solid var(--border); border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 10px; background: var(--surface-2); }
.mtools { display: flex; gap: 6px; }
.mlist { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 14px; max-height: 220px; overflow-y: auto; padding: 2px; font-family: var(--mono); }
.manual { display: flex; gap: 6px; }
.sel-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.ferr { display: flex; gap: 6px; align-items: center; color: var(--up); font-size: 12.5px; }
.hint { font-size: 12.5px; }
.mfoot { display: flex; justify-content: flex-end; gap: 8px; }
</style>
