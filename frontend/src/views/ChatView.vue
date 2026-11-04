<script setup lang="ts">
import { BookOpen, ChartLine, Layers, MessageSquarePlus, PanelLeft, PanelRightClose, Pencil, Send, Square, Trash2, Wand2, ArrowUpRight, GraduationCap, Shuffle } from 'lucide-vue-next'
import { NButton, NInput, NPopconfirm, NSpin, NTooltip, useMessage } from 'naive-ui'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { streamChat, type ChatEvent, type ModelRef } from '@/api/chat'
import { api, getBacktest, type BacktestPayload } from '@/api/client'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ModelPicker from '@/components/chat/ModelPicker.vue'
import { DISCLAIMER, type TextBlock, type ToolBlock, type UiMessage } from '@/components/chat/types'
import BacktestReport from '@/components/report/BacktestReport.vue'
import { useCatalog } from '@/stores/catalog'
import { timeAgo } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const toast = useMessage()
const catalog = useCatalog()

const sessions = ref<{ id: string; title: string; updated_at: string }[]>([])
const sessionId = ref<string | null>((route.params.sessionId as string) || null)
const messages = ref<UiMessage[]>([])
const input = ref('')
const busy = ref(false)
const loadingSession = ref(false)
const showSessions = ref(typeof window === 'undefined' || window.innerWidth > 900)
const scroller = ref<HTMLElement | null>(null)
const chatModel = ref<ModelRef | null>(null)
let abort: AbortController | null = null

// 右侧报告面板
const panelId = ref<string | null>(null)
const panelData = ref<BacktestPayload | null>(null)
const panelLoading = ref(false)

const suggestions = [
  { tone: 'blue', icon: Wand2, title: '调参 + 回测', text: '调出海龟交易期货策略，把 ATR 周期改为 22，单笔仓位上限 0.15，回测时间 2021-01-01 到 2024-12-30，标的选择国内商品期货主力合约' },
  { tone: 'amber', icon: Layers, title: '多策略组合', text: '选取双均线股票策略、动量选股策略，做等权组合，回测 2022-01-01 至 2025-06-30，对比沪深 300' },
  { tone: 'violet', icon: BookOpen, title: '算法教学', text: '给我讲下布林带股票策略原理，它的可调参数是什么' },
  { tone: 'teal', icon: ChartLine, title: '回测解读', text: '使用双均线策略，对沪深 A 股回测 2022-01-01 至 2025-12-31，并分析它在震荡市的表现' },
  { tone: 'rose', icon: GraduationCap, title: '概念问答', text: '海龟交易法则原理是什么，适合什么行情？' },
  { tone: 'teal', icon: Shuffle, title: '分散化', text: '把海龟交易法则和均值回归做等权组合回测 2021-01-01 到 2025-12-31，分析两者是否互补' },
]

async function loadSessions() {
  sessions.value = await api.get('/api/chat/sessions')
}

function fromServer(m: any): UiMessage {
  if (m.role === 'user') return { key: `u${m.id}`, role: 'user', text: m.content, blocks: [], switches: [] }
  const blocks: (ToolBlock | TextBlock)[] = []
  const switches: UiMessage['switches'] = []
  let factCheck = null
  for (const e of m.events as any[]) {
    if (e.kind === 'tool') blocks.push({ kind: 'tool', id: e.id, name: e.name, label: e.label, status: e.ok ? 'ok' : 'error', error: e.error, card: e.card })
    else if (e.kind === 'fact_check') factCheck = e
    else if (e.kind === 'model_switch') switches.push({ from: e.from, to: e.to, reason: e.reason })
  }
  let text: string = m.content
  const disclaimer = text.trimEnd().endsWith(DISCLAIMER)
  if (disclaimer) text = text.trimEnd().slice(0, -DISCLAIMER.length)
  blocks.push({ kind: 'text', text })
  return { key: `a${m.id}`, role: 'assistant', blocks, switches, factCheck, disclaimer, model: m.model }
}

async function openSession(id: string | null) {
  abort?.abort()
  sessionId.value = id
  messages.value = []
  panelId.value = null
  if (window.innerWidth <= 900) showSessions.value = false
  if (!id) return
  loadingSession.value = true
  try {
    const s = await api.get<any>(`/api/chat/sessions/${id}`)
    messages.value = s.messages.map(fromServer)
    await scrollToEnd(true)
  } catch (e: any) {
    toast.error(e.message)
    router.replace('/chat')
  } finally {
    loadingSession.value = false
  }
}

watch(() => route.params.sessionId, (id) => {
  const v = (id as string) || null
  if (v !== sessionId.value) openSession(v)
})

async function scrollToEnd(force = false) {
  await nextTick()
  const el = scroller.value
  if (!el) return
  const near = el.scrollHeight - el.scrollTop - el.clientHeight < 160
  if (force || near) el.scrollTop = el.scrollHeight
}

async function send(text?: string) {
  const content = (text ?? input.value).trim()
  if (!content || busy.value) return
  input.value = ''
  busy.value = true
  messages.value.push({ key: `u${Date.now()}`, role: 'user', text: content, blocks: [], switches: [] })
  const bot: UiMessage = { key: `a${Date.now()}`, role: 'assistant', blocks: [], streaming: true, switches: [], factCheck: null }
  messages.value.push(bot)
  const msg = messages.value[messages.value.length - 1] // 使用响应式代理
  await scrollToEnd(true)
  let roundStart = 0
  abort = new AbortController()

  const onEvent = (e: ChatEvent) => {
    switch (e.type) {
      case 'session':
        if (sessionId.value !== e.session_id) {
          sessionId.value = e.session_id
          router.replace(`/chat/${e.session_id}`)
        }
        break
      case 'model':
        msg.model = `${e.provider} / ${e.model}`
        roundStart = msg.blocks.length
        break
      case 'switch':
        msg.switches.push({ from: e.from, to: e.to, reason: e.reason })
        msg.blocks.splice(roundStart) // 丢弃失败模型已输出的片段
        break
      case 'delta': {
        const last = msg.blocks[msg.blocks.length - 1]
        if (last && last.kind === 'text') last.text += e.text
        else msg.blocks.push({ kind: 'text', text: e.text })
        break
      }
      case 'tool_start':
        msg.blocks.push({ kind: 'tool', id: e.id, name: e.name, label: e.label, status: 'running' })
        break
      case 'tool_end': {
        const b = msg.blocks.find((x) => x.kind === 'tool' && x.id === e.id) as ToolBlock | undefined
        if (b) Object.assign(b, { status: e.ok ? 'ok' : 'error', error: e.error, card: e.card, label: e.label })
        if (e.ok && e.card && (e.card.kind === 'backtest' || e.card.kind === 'portfolio')) openPanel(e.card.result_id)
        break
      }
      case 'fact_check':
        msg.factCheck = { status: e.status, checked: e.checked, unmatched: e.unmatched }
        break
      case 'disclaimer':
        msg.disclaimer = true
        break
      case 'error':
        msg.error = e.message
        break
      case 'done':
        if (!msg.blocks.some((b) => b.kind === 'text' && b.text.trim())) {
          let t: string = e.content ?? ''
          if (t.trimEnd().endsWith(DISCLAIMER)) t = t.trimEnd().slice(0, -DISCLAIMER.length)
          msg.blocks.push({ kind: 'text', text: t })
        }
        break
    }
    scrollToEnd()
  }

  try {
    await streamChat(content, sessionId.value, onEvent, abort.signal, chatModel.value)
  } catch (e: any) {
    if (e.name !== 'AbortError') msg.error = e.message || '连接中断'
    else msg.error = '已停止生成'
  } finally {
    msg.streaming = false
    busy.value = false
    abort = null
    loadSessions()
  }
}

function stop() {
  abort?.abort()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

async function openPanel(id: string) {
  panelId.value = id
  panelLoading.value = true
  try {
    panelData.value = await getBacktest(id)
  } catch (e: any) {
    toast.error(e.message)
    panelId.value = null
  } finally {
    panelLoading.value = false
  }
}

function newChat() {
  router.push('/chat')
  openSession(null)
}

const renaming = ref<string | null>(null)
const renameText = ref('')
async function rename(id: string) {
  if (!renameText.value.trim()) return (renaming.value = null)
  await api.patch(`/api/chat/sessions/${id}`, { title: renameText.value.trim() })
  renaming.value = null
  loadSessions()
}
async function remove(id: string) {
  await api.del(`/api/chat/sessions/${id}`)
  if (id === sessionId.value) newChat()
  loadSessions()
}

const empty = computed(() => !messages.value.length && !loadingSession.value)

onMounted(async () => {
  try {
    const pre = sessionStorage.getItem('chat-prefill')
    if (pre) { input.value = pre; sessionStorage.removeItem('chat-prefill') }
  } catch { /* 不可读时忽略 */ }
  catalog.load().catch(() => {})
  await loadSessions()
  if (sessionId.value) openSession(sessionId.value)
})
</script>

<template>
  <div class="chat-page" :class="{ 'with-panel': panelId }">
    <!-- 会话列表 -->
    <aside v-show="showSessions" class="sessions">
      <NButton block secondary type="primary" class="new" @click="newChat">
        <template #icon><MessageSquarePlus :size="16" /></template>新对话
      </NButton>
      <div class="s-list">
        <div v-if="!sessions.length" class="muted s-empty">还没有对话记录</div>
        <div
          v-for="s in sessions" :key="s.id" class="s-item" :class="{ active: s.id === sessionId }"
          @click="s.id !== sessionId && router.push(`/chat/${s.id}`)"
        >
          <template v-if="renaming === s.id">
            <NInput v-model:value="renameText" size="tiny" autofocus @keydown.enter="rename(s.id)" @blur="rename(s.id)" @click.stop />
          </template>
          <template v-else>
            <div class="s-title">{{ s.title }}</div>
            <div class="s-time">{{ timeAgo(s.updated_at) }}</div>
            <div class="s-ops" @click.stop>
              <button title="重命名" @click="renaming = s.id; renameText = s.title"><Pencil :size="13" /></button>
              <NPopconfirm @positive-click="remove(s.id)">
                <template #trigger><button title="删除"><Trash2 :size="13" /></button></template>
                删除这个对话？
              </NPopconfirm>
            </div>
          </template>
        </div>
      </div>
    </aside>

    <!-- 对话区 -->
    <section class="conv">
      <header class="conv-head">
        <NTooltip><template #trigger><button class="ghost" @click="showSessions = !showSessions"><PanelLeft :size="17" /></button></template>{{ showSessions ? '收起会话列表' : '展开会话列表' }}</NTooltip>
        <div class="conv-title">{{ sessions.find((s) => s.id === sessionId)?.title ?? '新对话' }}</div>
        <ModelPicker v-model="chatModel" />
      </header>

      <div ref="scroller" class="scroll">
        <div class="inner">
          <NSpin v-if="loadingSession" class="loading" />
          <div v-if="empty" class="aurora" aria-hidden="true"><span class="a1" /><span class="a2" /><span class="a3" /></div>
          <div v-if="empty" class="welcome">
            <div class="hero-icon"><span class="ring" /><img src="/logo.svg" width="44" height="44" alt="" /></div>
            <h1>你好，我是量化策略教学助手</h1>
            <p>用自然语言调取 22 种经典量化算法、修改参数、执行历史回测，我会解读报告并解释每一条优化建议背后的原理。</p>
            <RouterLink to="/learn" class="learn-chip"><GraduationCap :size="15" /> 第一次来？先看看零基础新手教程 <ArrowUpRight :size="14" /></RouterLink>
            <div class="sugs stagger">
              <button v-for="s in suggestions" :key="s.text" class="sug" :class="`tone-${s.tone}`" @click="send(s.text)">
                <div class="sug-title"><span class="ic-tile"><component :is="s.icon" :size="15" /></span> {{ s.title }}<ArrowUpRight :size="15" class="go" /></div>
                <div class="sug-text">{{ s.text }}</div>
              </button>
            </div>
          </div>
          <ChatMessage v-for="m in messages" :key="m.key" :msg="m" @open="openPanel" />
        </div>
      </div>

      <footer class="composer-wrap">
        <div class="composer">
          <NInput
            v-model:value="input" type="textarea" :autosize="{ minRows: 1, maxRows: 7 }" :bordered="false"
            placeholder="例如：把海龟策略的 ATR 周期改成 20，仓位上限 0.2，回测 2021 到 2024 年" @keydown="onKey"
          />
          <NButton v-if="busy" circle secondary type="error" @click="stop"><template #icon><Square :size="14" /></template></NButton>
          <NButton v-else circle type="primary" :disabled="!input.trim()" @click="send()"><template #icon><Send :size="15" /></template></NButton>
        </div>
        <div class="tip">Enter 发送 · Shift + Enter 换行 · 所有回测仅用于教学演示，不构成投资建议</div>
      </footer>
    </section>

    <!-- 回测报告面板 -->
    <aside v-if="panelId" class="panel">
      <div class="panel-head">
        <span>回测报告</span>
        <RouterLink :to="`/report/${panelId}`" target="_blank" class="open-full">新窗口打开</RouterLink>
        <button class="ghost" title="关闭" @click="panelId = null"><PanelRightClose :size="17" /></button>
      </div>
      <div class="panel-body">
        <NSpin v-if="panelLoading" class="loading" />
        <BacktestReport v-else-if="panelData" :key="panelData.id" :data="panelData" compact />
      </div>
    </aside>
  </div>
</template>

<style scoped>
.chat-page { display: flex; height: 100%; }
.sessions { width: 248px; flex-shrink: 0; border-right: 1px solid var(--border); background: var(--surface-2); display: flex; flex-direction: column; padding: 14px 10px; }
.new { margin-bottom: 10px; }
.s-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.s-empty { font-size: 12.5px; padding: 12px; text-align: center; }
.s-item { position: relative; padding: 8px 10px; border-radius: 9px; cursor: pointer; transition: background 0.15s, box-shadow 0.2s; animation: rise 0.35s var(--ease-out) both; }
.s-item:hover { background: var(--surface-3); }
.s-item.active { background: var(--surface); box-shadow: var(--shadow-sm); }
.s-title { font-size: 13px; color: var(--text-1); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; padding-right: 40px; }
.s-time { font-size: 11px; color: var(--text-3); }
.s-ops { position: absolute; right: 6px; top: 9px; display: none; gap: 2px; }
.s-item:hover .s-ops { display: flex; }
.s-ops button { border: none; background: none; color: var(--text-3); cursor: pointer; padding: 3px; border-radius: 5px; display: grid; }
.s-ops button:hover { color: var(--text-1); background: var(--surface); }

.conv { flex: 1; min-width: 0; display: flex; flex-direction: column; background: var(--bg); }
.conv-head { height: 52px; flex-shrink: 0; display: flex; align-items: center; gap: 10px; padding: 0 16px; border-bottom: 1px solid var(--border); background: var(--surface); }
.conv-title { font-weight: 600; font-size: 14.5px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; flex: 1; }
.ghost { border: none; background: none; color: var(--text-2); cursor: pointer; padding: 6px; border-radius: 7px; display: grid; }
.ghost:hover { background: var(--surface-3); color: var(--text-1); }
.scroll { flex: 1; overflow-y: auto; }
.inner { max-width: 860px; margin: 0 auto; padding: 8px 24px 24px; }
.loading { display: flex; justify-content: center; padding: 40px; }

.welcome { padding: 56px 0 20px; text-align: center; }
.welcome > * { animation: rise 0.55s var(--ease-out) both; }
.welcome > h1 { animation-delay: 0.06s; }
.welcome > p { animation-delay: 0.12s; }
.hero-icon {
  position: relative; display: inline-grid; place-items: center; width: 68px; height: 68px; border-radius: 20px; margin-bottom: 16px;
  background: linear-gradient(145deg, var(--surface), var(--primary-soft)); border: 1px solid var(--border);
  box-shadow: 0 10px 30px rgba(42, 120, 214, 0.18);
}
.hero-icon img { animation: float 4s ease-in-out infinite; }
.hero-icon .ring { position: absolute; inset: 0; border-radius: inherit; animation: pulse-ring 2.4s ease-out infinite; }
.welcome h1 {
  font-size: 26px; font-weight: 700; margin: 0 0 8px; letter-spacing: 0.3px;
  background: var(--brand-text); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.welcome p { color: var(--text-2); margin: 0 auto 14px; max-width: 560px; }
.learn-chip {
  display: inline-flex; align-items: center; gap: 6px; margin-bottom: 24px; padding: 5px 14px; border-radius: 999px; font-size: 13px; font-weight: 550;
  color: var(--t-amber); background: var(--t-amber-soft); border: 1px dashed color-mix(in srgb, var(--t-amber) 45%, transparent);
  transition: transform 0.25s var(--ease-out), box-shadow 0.25s;
}
.learn-chip:hover { transform: translateY(-2px); box-shadow: 0 6px 16px color-mix(in srgb, var(--t-amber) 25%, transparent); }
.welcome > .learn-chip { animation-delay: 0.16s; }
.sugs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; text-align: left; }
.sug { border: 1px solid var(--border); background: var(--surface); border-radius: 12px; padding: 12px 14px; cursor: pointer; font-family: inherit; color: inherit; transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s; text-align: left; }
.sug:hover { border-color: color-mix(in srgb, var(--tone) 50%, var(--border)); box-shadow: var(--shadow-md); transform: translateY(-3px); }
.sug-title svg { transition: transform 0.3s var(--ease-spring); }
.sug:hover .sug-title .ic-tile svg { transform: scale(1.2) rotate(-8deg); }
.sug { position: relative; overflow: hidden; background: color-mix(in srgb, var(--surface) 82%, transparent) !important; backdrop-filter: blur(8px); }
.sug::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--tone); transform: scaleY(0); transition: transform 0.3s var(--ease-out); }
.sug:hover::before { transform: scaleY(1); }
.sug-title { display: flex; align-items: center; gap: 9px; font-weight: 600; font-size: 13.5px; color: var(--text-1); margin-bottom: 6px; }
.sug-title .ic-tile { width: 28px; height: 28px; }
.go { margin-left: auto; color: var(--tone); opacity: 0; transform: translate(-4px, 4px); transition: opacity 0.2s, transform 0.3s var(--ease-out); }
.sug:hover .go { opacity: 1; transform: none; }
.inner { position: relative; }
.aurora { position: absolute; left: 50%; top: 0; width: 900px; max-width: 100%; height: 460px; transform: translateX(-50%); pointer-events: none; filter: blur(60px); opacity: 0.55; }
.aurora span { position: absolute; border-radius: 50%; animation: drift 16s ease-in-out infinite; }
.aurora .a1 { width: 320px; height: 220px; left: 12%; top: 30px; background: var(--t-blue-soft); background: color-mix(in srgb, var(--t-blue) 30%, transparent); }
.aurora .a2 { width: 280px; height: 200px; right: 12%; top: 70px; background: color-mix(in srgb, var(--t-violet) 26%, transparent); animation-delay: -5s; }
.aurora .a3 { width: 260px; height: 180px; left: 38%; top: 180px; background: color-mix(in srgb, var(--t-teal) 22%, transparent); animation-delay: -10s; }
.welcome { position: relative; }
.sug-text { font-size: 12.5px; color: var(--text-2); line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.composer-wrap { flex-shrink: 0; padding: 10px 24px 14px; }
.composer { max-width: 860px; margin: 0 auto; display: flex; align-items: flex-end; gap: 8px; background: var(--surface); border: 1px solid var(--border-strong); border-radius: 16px; padding: 8px 8px 8px 14px; box-shadow: var(--shadow-md); transition: border-color 0.15s; }
.composer { transition: border-color 0.2s, box-shadow 0.3s var(--ease-out); }
.composer:focus-within { border-color: var(--primary); box-shadow: 0 0 0 4px var(--primary-soft), var(--shadow-md); }
.composer :deep(.n-input) { background: transparent; }
.composer :deep(textarea) { font-size: 14px; line-height: 1.6; }
.tip { max-width: 860px; margin: 6px auto 0; font-size: 11.5px; color: var(--text-3); text-align: center; }

.panel { animation: panel-in 0.4s var(--ease-out) both; width: min(46%, 720px); min-width: 420px; flex-shrink: 0; border-left: 1px solid var(--border); background: var(--bg); display: flex; flex-direction: column; }
.panel-head { height: 52px; flex-shrink: 0; display: flex; align-items: center; gap: 12px; padding: 0 12px 0 18px; border-bottom: 1px solid var(--border); background: var(--surface); font-weight: 600; }
.open-full { margin-left: auto; font-size: 12.5px; font-weight: 400; }
.panel-body { flex: 1; overflow-y: auto; padding: 16px 18px 28px; }
@keyframes panel-in { from { opacity: 0; transform: translateX(24px); } to { opacity: 1; transform: none; } }
@media (max-width: 1280px) { .with-panel .sessions { display: none; } }
@media (max-width: 1000px) { .panel { position: fixed; inset: 0 0 0 64px; width: auto; min-width: 0; z-index: 20; } .sugs { grid-template-columns: 1fr; } }
@media (max-width: 900px) {
  .sessions { position: fixed; left: 64px; top: 0; bottom: 0; z-index: 15; box-shadow: var(--shadow-md); }
  .inner { padding: 8px 14px 20px; }
  .composer-wrap { padding: 8px 12px 10px; }
  .welcome { padding-top: 28px; }
  .welcome h1 { font-size: 20px; }
}
</style>
