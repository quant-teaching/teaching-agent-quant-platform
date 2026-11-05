<script setup lang="ts">
// 我的模型：老师、学生自己添加的 OpenAI 兼容渠道。只有自己能看到和使用，Key 只保存在服务器、不回传；使用时不占平台额度
import { CircleCheck, CircleX, Loader2, Pencil, Plus, RefreshCw, Server, Trash2, Zap } from 'lucide-vue-next'
import { NButton, NEmpty, NForm, NFormItem, NInput, NModal, NPopconfirm, NSwitch, NTag, useMessage } from 'naive-ui'
import { onMounted, reactive, ref } from 'vue'
import { api, type Provider } from '@/api/client'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
const toast = useMessage()
const list = ref<Provider[]>([])
const loading = ref(true)
const tests = reactive<Record<string, { loading?: boolean; ok?: boolean; latency_ms?: number; tool_calling?: boolean; error?: string }>>({})

async function load() {
  loading.value = true
  try { list.value = await api.get<Provider[]>('/api/llm/my-providers') } catch (e: any) { toast.error(e.message) } finally { loading.value = false }
}
onMounted(load)

const form = reactive({ show: false, id: null as number | null, name: '', base_url: '', api_key: '', models: [] as string[], manual: '',
  fetched: [] as string[], fetching: false, saving: false })
function open(p?: Provider) {
  Object.assign(form, { show: true, id: p?.id ?? null, name: p?.name ?? '', base_url: p?.base_url ?? 'https://', api_key: '',
    models: [...(p?.models ?? [])], manual: '', fetched: [], fetching: false })
}
async function fetchModels() {
  form.fetching = true
  try {
    const r = await api.post<{ base_url: string; models: string[] }>('/api/llm/my-providers/fetch',
      { base_url: form.base_url, api_key: form.api_key || null, provider_id: form.id })
    form.base_url = r.base_url
    form.fetched = r.models
    if (!form.models.length) form.models = r.models.slice(0, 3)
    toast.success(`获取到 ${r.models.length} 个模型`)
  } catch (e: any) { toast.error(e.message) } finally { form.fetching = false }
}
function toggle(m: string) {
  form.models = form.models.includes(m) ? form.models.filter((x) => x !== m) : [...form.models, m]
}
function addManual() {
  const m = form.manual.trim()
  if (m && !form.models.includes(m)) form.models.push(m)
  form.manual = ''
}
async function save() {
  if (!form.models.length) return toast.error('请至少选择或填写一个模型')
  form.saving = true
  try {
    const body = { name: form.name.trim(), base_url: form.base_url.trim(), api_key: form.api_key.trim() || null, models: form.models }
    if (form.id) await api.put(`/api/llm/my-providers/${form.id}`, body)
    else await api.post('/api/llm/my-providers', body)
    toast.success('已保存，可以在智能助手的模型选择里使用')
    form.show = false
    load()
  } catch (e: any) { toast.error(e.message) } finally { form.saving = false }
}
async function setEnabled(p: Provider, v: boolean) {
  try { Object.assign(p, await api.put<Provider>(`/api/llm/my-providers/${p.id}`, { enabled: v })) } catch (e: any) { toast.error(e.message) }
}
async function remove(p: Provider) {
  try { await api.del(`/api/llm/my-providers/${p.id}`); toast.success('已删除'); load() } catch (e: any) { toast.error(e.message) }
}
async function test(p: Provider, m: string) {
  const k = `${p.id}:${m}`
  tests[k] = { loading: true }
  try { tests[k] = await api.post(`/api/llm/my-test`, { provider_id: p.id, model: m }) } catch (e: any) { tests[k] = { ok: false, error: e.message } }
}
</script>

<template>
  <div class="panel-body">
    <section v-if="!auth.user?.allow_own" class="card card-pad">
      <NEmpty description="管理员关闭了你使用自己模型渠道的权限，如有需要请联系老师或管理员" />
    </section>
    <template v-else>
      <section class="card card-pad intro">
        <div>
          <h3 class="section-title"><Server :size="16" class="ti" /> 我的模型渠道</h3>
          <p class="section-sub">可以接入自己的 OpenAI 兼容接口（如 DeepSeek、通义千问、硅基流动）。只有你自己能看到和使用，API Key 只保存在服务器上、不会回传到页面；使用自己的渠道<b>不占用平台额度</b>。出于安全原因，地址只能是公网地址。</p>
        </div>
        <NButton type="primary" @click="open()"><template #icon><Plus :size="16" /></template>添加渠道</NButton>
      </section>

      <NEmpty v-if="!loading && !list.length" description="还没有添加自己的模型渠道" class="card card-pad" />
      <div class="grid stagger">
        <article v-for="p in list" :key="p.id" class="card card-pad prov" :class="{ off: !p.enabled }">
          <header>
            <span class="ic-tile tone-teal"><Server :size="16" /></span>
            <div class="pt"><b>{{ p.name }}</b><em>{{ p.base_url }}</em></div>
            <NSwitch size="small" :value="p.enabled" @update:value="(v: boolean) => setEnabled(p, v)" />
          </header>
          <div class="models">
            <div v-for="m in p.models" :key="m" class="m-row">
              <code>{{ m }}</code>
              <span class="sp" />
              <template v-if="tests[`${p.id}:${m}`]">
                <Loader2 v-if="tests[`${p.id}:${m}`].loading" :size="14" class="spin" />
                <span v-else-if="tests[`${p.id}:${m}`].ok" class="t-ok"><CircleCheck :size="14" /> {{ tests[`${p.id}:${m}`].latency_ms }} ms{{ tests[`${p.id}:${m}`].tool_calling ? ' · 支持工具' : ' · 不支持工具调用' }}</span>
                <span v-else class="t-bad" :title="tests[`${p.id}:${m}`].error"><CircleX :size="14" /> 失败</span>
              </template>
              <NButton size="tiny" quaternary @click="test(p, m)"><template #icon><Zap :size="13" /></template>测试</NButton>
            </div>
          </div>
          <footer>
            <NTag size="small" :bordered="false" round>Key {{ p.api_key_masked || '未设置' }}</NTag>
            <span class="sp" />
            <NButton size="small" quaternary @click="open(p)"><template #icon><Pencil :size="14" /></template>编辑</NButton>
            <NPopconfirm @positive-click="remove(p)">
              <template #trigger><NButton size="small" quaternary type="error"><template #icon><Trash2 :size="14" /></template>删除</NButton></template>
              删除「{{ p.name }}」？
            </NPopconfirm>
          </footer>
        </article>
      </div>
    </template>

    <NModal v-model:show="form.show" preset="card" :title="form.id ? '编辑模型渠道' : '添加模型渠道'" :bordered="false" style="width: 560px; max-width: calc(100vw - 32px)">
      <NForm label-placement="top" @submit.prevent="save">
        <NFormItem label="名称"><NInput v-model:value="form.name" :maxlength="30" placeholder="便于识别，如：我的 DeepSeek" /></NFormItem>
        <NFormItem label="API 地址"><NInput v-model:value="form.base_url" placeholder="https://api.deepseek.com/v1" /></NFormItem>
        <NFormItem :label="form.id ? 'API Key（留空表示不修改）' : 'API Key'"><NInput v-model:value="form.api_key" type="password" show-password-on="click" placeholder="sk-..." /></NFormItem>
        <div class="fm-models">
          <div class="fm-h"><b>模型</b>
            <NButton size="small" secondary :loading="form.fetching" @click="fetchModels"><template #icon><RefreshCw :size="14" /></template>获取模型列表</NButton>
          </div>
          <div v-if="form.fetched.length" class="chips">
            <button v-for="m in form.fetched" :key="m" type="button" class="chip" :class="{ on: form.models.includes(m) }" @click="toggle(m)">{{ m }}</button>
          </div>
          <div class="manual"><NInput v-model:value="form.manual" size="small" placeholder="也可以手动填写模型名，回车添加" @keydown.enter.prevent="addManual" /></div>
          <div class="sel"><NTag v-for="m in form.models" :key="m" size="small" closable round @close="toggle(m)">{{ m }}</NTag></div>
        </div>
        <NButton type="primary" block attr-type="submit" :loading="form.saving">保存</NButton>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.intro { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.ti { vertical-align: -2px; margin-right: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.prov { display: flex; flex-direction: column; gap: 10px; }
.prov.off { opacity: 0.6; }
.prov header { display: flex; align-items: center; gap: 10px; }
.pt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.pt b { font-size: 14.5px; }
.pt em { font-style: normal; font-size: 12px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.models { display: flex; flex-direction: column; gap: 4px; }
.m-row { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 8px; background: var(--surface-2); font-size: 12.5px; }
.m-row code { font-family: var(--mono); }
.sp { flex: 1; }
.t-ok { display: inline-flex; align-items: center; gap: 3px; color: var(--c-tip); }
.t-bad { display: inline-flex; align-items: center; gap: 3px; color: var(--up); cursor: help; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.prov footer { display: flex; align-items: center; gap: 4px; }
.fm-models { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.fm-h { display: flex; justify-content: space-between; align-items: center; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; max-height: 150px; overflow-y: auto; }
.chip { border: 1px solid var(--border); background: var(--surface); border-radius: 999px; padding: 2px 10px; font: inherit; font-size: 12px; cursor: pointer; }
.chip.on { border-color: var(--primary); color: var(--primary-ink); background: var(--primary-soft); }
.sel { display: flex; flex-wrap: wrap; gap: 6px; }
@media (max-width: 700px) { .intro { flex-direction: column; } }
</style>
