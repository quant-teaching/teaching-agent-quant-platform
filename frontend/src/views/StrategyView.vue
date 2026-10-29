<script setup lang="ts">
import { ArrowLeft, FlaskConical, MessageSquareText, Save, Trash2 } from 'lucide-vue-next'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import { NButton, NInput, NModal, NPopconfirm, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type StrategyDetail } from '@/api/client'
import MarkdownView from '@/components/common/MarkdownView.vue'
import ParamForm from '@/components/common/ParamForm.vue'
import { useCatalog } from '@/stores/catalog'
import { universeLabel } from '@/utils/format'

hljs.registerLanguage('python', python)
const route = useRoute()
const router = useRouter()
const toast = useMessage()
const catalog = useCatalog()
const s = ref<StrategyDetail | null>(null)
const params = ref<Record<string, any>>({})
const tab = ref('doc')

onMounted(async () => {
  try {
    s.value = await api.get<StrategyDetail>(`/api/strategies/${route.params.id}`)
    params.value = Object.fromEntries(s.value.params.map((p) => [p.key, p.default]))
  } catch (e: any) {
    toast.error(e.message)
    router.replace('/library')
  }
})

const code = computed(() => (s.value ? hljs.highlight(s.value.source, { language: 'python' }).value : ''))
const changed = computed(() => (s.value ? s.value.params.filter((p) => params.value[p.key] !== p.default).length : 0))

function backtest() {
  router.push({ path: '/backtest', query: { strategy: s.value!.id, params: JSON.stringify(params.value) } })
}
function ask() {
  try { sessionStorage.setItem('chat-prefill', `给我讲讲${s.value!.name}的原理，它适合什么行情？`) } catch { /* 不可写时忽略 */ }
  router.push('/chat')
}

const saveDlg = ref(false)
const derivedName = ref('')
const derivedDesc = ref('')
async function saveDerived() {
  try {
    const info = await api.post<any>('/api/strategies/derived', { base: s.value!.id, name: derivedName.value, params: params.value, description: derivedDesc.value })
    toast.success(`已保存「${info.name}」`)
    saveDlg.value = false
    await catalog.load(true)
    router.push(`/library/${info.id}`)
  } catch (e: any) {
    toast.error(e.message)
  }
}
async function removeDerived() {
  await api.del(`/api/strategies/derived/${s.value!.id}`)
  toast.success('已删除')
  await catalog.load(true)
  router.replace('/library')
}
</script>

<template>
  <div class="page">
    <NSpin :show="!s">
      <template v-if="s">
        <RouterLink to="/library" class="back"><ArrowLeft :size="15" /> 返回算法库</RouterLink>
        <div class="page-head">
          <div>
            <div class="tags">
              <span class="cat" :class="s.category">{{ s.category_label }}</span>
              <span class="tag-soft">{{ s.style }}</span>
              <span v-if="s.derived" class="tag-soft">基于 {{ s.base_name }}</span>
              <span class="tag-soft">默认标的：{{ universeLabel(s.default_universe) }}</span>
            </div>
            <h1>{{ s.name }}</h1>
            <p>{{ s.summary }}</p>
          </div>
          <div class="acts">
            <NButton @click="ask"><template #icon><MessageSquareText :size="15" /></template>问助手</NButton>
            <NButton type="primary" @click="backtest"><template #icon><FlaskConical :size="15" /></template>用当前参数回测</NButton>
          </div>
        </div>

        <NTabs v-model:value="tab" type="line" animated>
          <NTabPane name="doc" tab="教学说明">
            <div class="card card-pad doc"><MarkdownView :source="s.doc || '暂无说明文档'" /></div>
          </NTabPane>
          <NTabPane name="params" :tab="`参数（${s.params.length}）`">
            <div class="card card-pad">
              <div class="p-head">
                <div>
                  <h3 class="section-title">可调参数</h3>
                  <p class="section-sub">悬停参数名查看详细说明；修改过的参数会高亮显示{{ changed ? `，当前已修改 ${changed} 项` : '' }}</p>
                </div>
                <div class="acts">
                  <NButton v-if="!s.derived" secondary :disabled="!changed" @click="saveDlg = true; derivedName = `${s.name}（自定义）`"><template #icon><Save :size="15" /></template>另存为衍生策略</NButton>
                  <NPopconfirm v-else @positive-click="removeDerived">
                    <template #trigger><NButton secondary type="error"><template #icon><Trash2 :size="15" /></template>删除衍生策略</NButton></template>
                    确定删除「{{ s.name }}」？
                  </NPopconfirm>
                  <NButton type="primary" @click="backtest"><template #icon><FlaskConical :size="15" /></template>回测</NButton>
                </div>
              </div>
              <ParamForm v-model="params" :specs="s.params" />
            </div>
          </NTabPane>
          <NTabPane name="source" tab="源码">
            <div class="card code-card">
              <div class="code-head"><span class="muted">backend/quant/strategies/{{ s.category === 'futures' ? 'futures' : 'stock' }}/{{ s.source_file }}</span></div>
              <!-- eslint-disable-next-line vue/no-v-html -->
              <pre class="code"><code v-html="code" /></pre>
            </div>
          </NTabPane>
        </NTabs>
      </template>
    </NSpin>

    <NModal v-model:show="saveDlg" preset="card" title="另存为衍生策略" style="width: 480px" :bordered="false">
      <div class="dlg">
        <p class="muted">把当前修改过的参数保存为一个新策略，之后可以在算法库、回测实验室和对话中按名字调取。</p>
        <NInput v-model:value="derivedName" placeholder="策略名称" />
        <NInput v-model:value="derivedDesc" type="textarea" placeholder="说明（可选），如：拉长通道周期，减少震荡市假突破" :autosize="{ minRows: 2 }" />
      </div>
      <template #footer><div class="dlg-foot"><NButton @click="saveDlg = false">取消</NButton><NButton type="primary" @click="saveDerived">保存</NButton></div></template>
    </NModal>
  </div>
</template>

<style scoped>
.page { max-width: 1180px; }
.back { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: var(--text-3); margin-bottom: 12px; }
.back:hover { color: var(--primary); }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.cat { padding: 1px 8px; border-radius: 6px; font-weight: 600; font-size: 12px; }
.cat.stock { background: var(--primary-soft); color: var(--primary-ink); }
.cat.futures { background: var(--warn-soft); color: var(--warn); }
.page-head p { font-size: 14px; color: var(--text-2); max-width: 760px; }
.acts { display: flex; gap: 8px; flex-wrap: wrap; }
.doc { max-width: 920px; padding: 24px 32px; }
.p-head { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.code-card { overflow: hidden; }
.code-head { padding: 10px 16px; border-bottom: 1px solid var(--border); font-family: var(--mono); font-size: 12px; background: var(--surface-2); }
.code { margin: 0; padding: 16px 20px; overflow-x: auto; font-family: var(--mono); font-size: 12.5px; line-height: 1.65; background: var(--surface); color: var(--text-1); }
.dlg { display: flex; flex-direction: column; gap: 10px; }
.dlg p { margin: 0; font-size: 13px; }
.dlg-foot { display: flex; justify-content: flex-end; gap: 8px; }
</style>
