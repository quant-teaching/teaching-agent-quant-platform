<script setup lang="ts">
// 对话列表：按时间分组；顶部搜索（标题 + 对话内容，命中片段高亮，上下键选择、回车打开）；
// 「管理」模式下多选（Shift 连选、全选）并批量删除。
import { Check, CheckCheck, ListChecks, MessageSquarePlus, MessagesSquare, Pencil, SearchX, Trash2, User, Bot, X } from 'lucide-vue-next'
import { NButton, NInput, NPopconfirm, useMessage } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '@/api/client'
import HighlightText from '@/components/common/HighlightText.vue'
import SearchBox from '@/components/common/SearchBox.vue'
import { timeAgo } from '@/utils/format'

export interface SessionRow { id: string; title: string; updated_at: string }
interface Hit extends SessionRow { hits: number; snippet: string | null; snippet_role: string | null }

const props = defineProps<{ sessions: SessionRow[]; current: string | null }>()
const emit = defineEmits<{ open: [id: string, q?: string]; new: []; changed: []; deleted: [ids: string[]] }>()
const toast = useMessage()

// ---------------- 搜索
const q = ref('')
const hits = ref<Hit[] | null>(null)
const searching = ref(false)
const cursor = ref(0)
let timer: number | undefined
let seq = 0
function search(v: string, delay = 220) {
  window.clearTimeout(timer)
  cursor.value = 0
  if (!v.trim()) { hits.value = null; searching.value = false; return }
  searching.value = true
  timer = window.setTimeout(async () => {
    const my = ++seq
    try {
      const r = await api.get<Hit[]>(`/api/chat/sessions?q=${encodeURIComponent(v.trim())}`)
      if (my === seq) hits.value = r
    } catch (e: any) {
      if (my === seq) toast.error(e.message)
    } finally {
      if (my === seq) searching.value = false
    }
  }, delay)
}
watch(q, (v) => search(v))
onBeforeUnmount(() => window.clearTimeout(timer))
// 对话列表变了（新建、删除、改名）时刷新搜索结果
watch(() => props.sessions, () => { if (q.value.trim()) search(q.value, 0) })

function openHit(h: Hit) { emit('open', h.id, q.value.trim()) }
function moveCursor(d: number) {
  const n = hits.value?.length ?? 0
  if (!n) return
  cursor.value = (cursor.value + d + n) % n
  document.querySelector(`.sl [data-hit="${cursor.value}"]`)?.scrollIntoView({ block: 'nearest' })
}
function enterHit() { const h = hits.value?.[cursor.value]; if (h) openHit(h) }

// ---------------- 按时间分组
const groups = computed(() => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const DAY = 86400000
  const defs: { key: string; label: string; test: (t: number) => boolean }[] = [
    { key: 'today', label: '今天', test: (t) => t >= today },
    { key: 'yesterday', label: '昨天', test: (t) => t >= today - DAY },
    { key: 'week', label: '近 7 天', test: (t) => t >= today - 6 * DAY },
    { key: 'month', label: '近 30 天', test: (t) => t >= today - 29 * DAY },
    { key: 'older', label: '更早', test: () => true },
  ]
  const out = defs.map((d) => ({ ...d, items: [] as SessionRow[] }))
  for (const s of props.sessions) {
    const t = new Date(s.updated_at).getTime()
    out.find((g) => g.test(t))!.items.push(s)
  }
  return out.filter((g) => g.items.length)
})
const flat = computed(() => groups.value.flatMap((g) => g.items))

// ---------------- 多选管理
const managing = ref(false)
const picked = ref(new Set<string>())
let anchor: string | null = null
function startManage() { managing.value = true; picked.value = new Set(); anchor = null; q.value = '' }
function endManage() { managing.value = false; picked.value = new Set() }
function pick(id: string, e: MouseEvent) {
  const s = new Set(picked.value)
  if (e.shiftKey && anchor) {
    const ids = flat.value.map((x) => x.id)
    const [a, b] = [ids.indexOf(anchor), ids.indexOf(id)].sort((x, y) => x - y)
    const on = !s.has(id)
    for (const x of ids.slice(a, b + 1)) on ? s.add(x) : s.delete(x)
  } else {
    s.has(id) ? s.delete(id) : s.add(id)
  }
  anchor = id
  picked.value = s
}
const allPicked = computed(() => flat.value.length > 0 && picked.value.size === flat.value.length)
function pickAll() { picked.value = allPicked.value ? new Set() : new Set(flat.value.map((x) => x.id)) }
function pickGroup(items: SessionRow[]) {
  const s = new Set(picked.value)
  const all = items.every((x) => s.has(x.id))
  for (const x of items) all ? s.delete(x.id) : s.add(x.id)
  picked.value = s
}
const deleting = ref(false)
async function removePicked() {
  const ids = [...picked.value]
  if (!ids.length) return
  deleting.value = true
  try {
    const r = await api.post<{ deleted: number }>('/api/chat/sessions/batch-delete', { ids })
    toast.success(`已删除 ${r.deleted} 个对话`)
    emit('deleted', ids)
    endManage()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    deleting.value = false
  }
}
function onKey(e: KeyboardEvent) { if (e.key === 'Escape' && managing.value) endManage() }
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// ---------------- 单个重命名 / 删除
const renaming = ref<string | null>(null)
const renameText = ref('')
async function rename(id: string) {
  const t = renameText.value.trim()
  renaming.value = null
  if (!t) return
  await api.patch(`/api/chat/sessions/${id}`, { title: t })
  emit('changed')
}
async function removeOne(id: string) {
  await api.del(`/api/chat/sessions/${id}`)
  emit('deleted', [id])
}
function clickItem(s: SessionRow, e: MouseEvent) {
  if (managing.value) pick(s.id, e)
  else if (s.id !== props.current) emit('open', s.id)
}
</script>

<template>
  <div class="sl" :class="{ managing }">
    <div class="sl-top">
      <NButton block secondary type="primary" class="new" @click="emit('new')">
        <template #icon><MessageSquarePlus :size="16" /></template>新对话
      </NButton>
      <div class="sl-search">
        <SearchBox v-model="q" size="sm" hotkey placeholder="搜索对话标题和内容" :count="hits ? hits.length : null" :loading="searching"
                   @move="moveCursor" @enter="enterHit" />
        <button class="mg" :class="{ on: managing }" :title="managing ? '退出管理（Esc）' : '多选管理'" @click="managing ? endManage() : startManage()">
          <X v-if="managing" :size="15" /><ListChecks v-else :size="15" />
        </button>
      </div>
    </div>

    <div class="sl-body">
      <!-- 搜索结果 -->
      <template v-if="hits !== null">
        <div v-if="!hits.length && !searching" class="sl-empty">
          <SearchX :size="28" :stroke-width="1.6" />
          <div>没有找到包含「{{ q.trim() }}」的对话</div>
          <span>试试更短的关键词，比如策略名或指标名</span>
        </div>
        <TransitionGroup name="sl-item" tag="div" class="sl-hits">
          <div v-for="(h, i) in hits" :key="h.id" :data-hit="i" class="hit" :class="{ active: h.id === current, cur: i === cursor }"
               :style="{ animationDelay: `${Math.min(i, 10) * 25}ms` }" @click="openHit(h)" @mouseenter="cursor = i">
            <div class="hit-title"><HighlightText :text="h.title" :q="q" /></div>
            <div v-if="h.snippet" class="hit-snip">
              <span class="who" :class="h.snippet_role"><User v-if="h.snippet_role === 'user'" :size="11" /><Bot v-else :size="11" /></span>
              <HighlightText :text="h.snippet" :q="q" />
            </div>
            <div class="hit-meta"><span>{{ timeAgo(h.updated_at) }}</span><span v-if="h.hits">{{ h.hits }} 处命中</span></div>
          </div>
        </TransitionGroup>
      </template>

      <!-- 按时间分组的对话 -->
      <template v-else>
        <div v-if="!sessions.length" class="sl-empty"><MessagesSquare :size="28" :stroke-width="1.6" /><div>还没有对话记录</div><span>在右侧输入问题，开始第一次对话</span></div>
        <section v-for="g in groups" :key="g.key" class="grp">
          <div class="grp-head">
            <span>{{ g.label }}</span>
            <button v-if="managing" class="grp-pick" @click="pickGroup(g.items)">{{ g.items.every((x) => picked.has(x.id)) ? '取消本组' : '选择本组' }}</button>
            <span v-else class="grp-n">{{ g.items.length }}</span>
          </div>
          <TransitionGroup name="sl-item" tag="div">
            <div v-for="s in g.items" :key="s.id" class="s-item" :class="{ active: !managing && s.id === current, picked: picked.has(s.id) }" @click="clickItem(s, $event)">
              <Transition name="ck"><span v-if="managing" class="ck"><Check :size="11" :stroke-width="3.4" /></span></Transition>
              <div class="s-main">
                <template v-if="renaming === s.id">
                  <NInput v-model:value="renameText" size="tiny" autofocus @keydown.enter="rename(s.id)" @keydown.esc="renaming = null" @blur="rename(s.id)" @click.stop />
                </template>
                <template v-else>
                  <div class="s-title">{{ s.title }}</div>
                  <div class="s-time">{{ timeAgo(s.updated_at) }}</div>
                </template>
              </div>
              <div v-if="!managing && renaming !== s.id" class="s-ops" @click.stop>
                <button title="重命名" @click="renaming = s.id; renameText = s.title"><Pencil :size="13" /></button>
                <NPopconfirm @positive-click="removeOne(s.id)">
                  <template #trigger><button title="删除" class="del"><Trash2 :size="13" /></button></template>
                  删除这个对话？
                </NPopconfirm>
              </div>
            </div>
          </TransitionGroup>
        </section>
      </template>
    </div>

    <!-- 批量操作栏 -->
    <Transition name="bar">
      <div v-if="managing" class="bar">
        <div class="bar-info">
          <button class="bar-all" @click="pickAll"><CheckCheck :size="14" />{{ allPicked ? '取消全选' : '全选' }}</button>
          <span>已选 <b :key="picked.size" class="n">{{ picked.size }}</b> 项</span>
        </div>
        <div class="bar-acts">
          <NPopconfirm :disabled="!picked.size" @positive-click="removePicked">
            <template #trigger>
              <NButton size="small" type="error" :disabled="!picked.size" :loading="deleting"><template #icon><Trash2 :size="14" /></template>删除</NButton>
            </template>
            删除选中的 {{ picked.size }} 个对话？删除后无法恢复。
          </NPopconfirm>
          <NButton size="small" secondary @click="endManage">完成</NButton>
        </div>
        <div class="bar-tip">点击选择，按住 Shift 可连选</div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.sl { position: relative; display: flex; flex-direction: column; height: 100%; min-height: 0; }
.sl-top { display: flex; flex-direction: column; gap: 10px; padding-bottom: 10px; }
.sl-search { display: flex; gap: 6px; align-items: center; }
.sl-search > :first-child { flex: 1; min-width: 0; }
.mg {
  flex-shrink: 0; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-2); cursor: pointer; transition: all 0.2s var(--ease-out);
}
.mg:hover { color: var(--primary-ink); border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); }
.mg.on { background: var(--primary); color: #fff; border-color: var(--primary); transform: rotate(90deg); }

.sl-body { flex: 1; min-height: 0; overflow-y: auto; margin: 0 -4px; padding: 0 4px; }
.managing .sl-body { padding-bottom: 118px; }
.grp + .grp { margin-top: 8px; }
.grp-head { position: sticky; top: 0; z-index: 1; display: flex; justify-content: space-between; align-items: center; padding: 6px 8px 4px; font-size: 11.5px; font-weight: 600; color: var(--text-3); background: var(--surface-2); }
.grp-n { font-weight: 500; font-variant-numeric: tabular-nums; }
.grp-pick { border: none; background: none; color: var(--primary-ink); font-size: 11.5px; cursor: pointer; padding: 0; }
.grp-pick:hover { text-decoration: underline; }

.s-item {
  position: relative; display: flex; align-items: center; gap: 9px; padding: 8px 10px; border-radius: 9px; cursor: pointer;
  transition: background 0.15s, box-shadow 0.2s, transform 0.2s var(--ease-out);
}
.s-item:hover { background: var(--surface-3); }
.s-item.active { background: var(--surface); box-shadow: var(--shadow-sm); }
.s-item.active::before { content: ''; position: absolute; left: 0; top: 22%; bottom: 22%; width: 3px; border-radius: 3px; background: var(--primary); }
.s-item.picked { background: var(--primary-soft); }
.managing .s-item { user-select: none; }
.managing .s-item:active { transform: scale(0.98); }
.s-main { flex: 1; min-width: 0; }
.s-title { font-size: 13px; color: var(--text-1); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; padding-right: 40px; }
.managing .s-title { padding-right: 0; }
.s-time { font-size: 11px; color: var(--text-3); }
.s-ops { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s; }
.s-item:hover .s-ops { opacity: 1; }
.s-ops button { border: none; background: none; color: var(--text-3); cursor: pointer; padding: 4px; border-radius: 6px; display: grid; transition: color 0.15s, background 0.15s; }
.s-ops button:hover { color: var(--text-1); background: var(--surface); }
.s-ops button.del:hover { color: var(--danger, #d03050); }

.ck {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 6px; border: 1.6px solid color-mix(in srgb, var(--text-3) 70%, transparent);
  display: grid; place-items: center; color: transparent; background: var(--surface); transition: all 0.2s var(--ease-spring);
}
.s-item:hover .ck { border-color: var(--primary); }
.picked .ck { background: var(--primary); border-color: var(--primary); color: #fff; transform: scale(1.08); }
.ck svg { transform: scale(0); transition: transform 0.25s var(--ease-spring); }
.picked .ck svg { transform: scale(1); }
.ck-enter-active { transition: opacity 0.2s, transform 0.3s var(--ease-spring), width 0.25s var(--ease-out), margin 0.25s; }
.ck-leave-active { transition: opacity 0.15s, transform 0.15s, width 0.2s, margin 0.2s; }
.ck-enter-from, .ck-leave-to { opacity: 0; transform: scale(0.3); width: 0; margin-right: -9px; }

/* 搜索结果 */
.hit { padding: 9px 10px; border-radius: 10px; cursor: pointer; border: 1px solid transparent; animation: sl-in 0.3s var(--ease-out) both; transition: background 0.15s, border-color 0.15s; }
.hit + .hit { margin-top: 2px; }
.hit.cur { background: var(--surface); border-color: var(--border); box-shadow: var(--shadow-sm); }
.hit.active .hit-title { color: var(--primary-ink); }
.hit-title { font-size: 13px; font-weight: 600; color: var(--text-1); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.hit-snip { display: flex; gap: 6px; margin-top: 4px; font-size: 12px; line-height: 1.55; color: var(--text-2); }
.hit-snip > span:last-child { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.who { flex-shrink: 0; width: 17px; height: 17px; border-radius: 5px; display: grid; place-items: center; margin-top: 1px; background: var(--surface-3); color: var(--text-3); }
.who.user { background: var(--primary-soft); color: var(--primary-ink); }
.hit-meta { display: flex; justify-content: space-between; margin-top: 5px; font-size: 11px; color: var(--text-3); }
.sl-empty { display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; padding: 36px 12px; color: var(--text-3); animation: sl-in 0.35s var(--ease-out) both; }
.sl-empty div { font-size: 13px; color: var(--text-2); }
.sl-empty span { font-size: 11.5px; }
@keyframes sl-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.sl-item-move { transition: transform 0.3s var(--ease-out); }
.sl-item-enter-active { transition: opacity 0.25s, transform 0.3s var(--ease-out); }
.sl-item-leave-active { transition: opacity 0.2s, transform 0.25s; position: absolute; width: calc(100% - 8px); }
.sl-item-enter-from { opacity: 0; transform: translateY(-6px); }
.sl-item-leave-to { opacity: 0; transform: translateX(-24px); }

/* 底部批量操作栏 */
.bar {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 3; padding: 10px 12px; border-radius: 14px;
  background: var(--surface); border: 1px solid var(--border); box-shadow: 0 -8px 28px rgba(15, 23, 42, 0.12);
  display: flex; flex-direction: column; gap: 8px;
}
.bar-info { display: flex; justify-content: space-between; align-items: center; font-size: 12.5px; color: var(--text-2); }
.bar-info .n { display: inline-block; color: var(--primary-ink); font-variant-numeric: tabular-nums; animation: bump 0.3s var(--ease-spring); }
@keyframes bump { from { transform: scale(1.5); } }
.bar-all { display: inline-flex; align-items: center; gap: 4px; border: none; background: none; color: var(--primary-ink); cursor: pointer; font-size: 12.5px; padding: 0; }
.bar-all:hover { text-decoration: underline; }
.bar-acts { display: flex; gap: 8px; }
.bar-acts > * { flex: 1; }
.bar-tip { font-size: 11px; color: var(--text-3); text-align: center; }
.bar-enter-active { transition: opacity 0.25s, transform 0.35s var(--ease-spring); }
.bar-leave-active { transition: opacity 0.15s, transform 0.2s; }
.bar-enter-from, .bar-leave-to { opacity: 0; transform: translateY(24px) scale(0.96); }
</style>
