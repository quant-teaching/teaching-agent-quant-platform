<script setup lang="ts">
// 新手教程：/learn 为目录页（按分类排列的章节卡片），/learn/:id 为章节页（左侧目录 + 格子纸正文 + 上下章）
import { Presentation, AArrowDown, AArrowUp, ArrowLeft, ArrowRight, BookOpenCheck, Check, ChevronDown, ChevronUp, Clock, Search, SearchX, X, Compass, GraduationCap, ListTree, Maximize, Minimize, PanelLeftClose, PanelLeftOpen, Rocket, Sprout, Wrench } from 'lucide-vue-next'
import { NButton, NProgress } from 'naive-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import HighlightText from '@/components/common/HighlightText.vue'
import MarkdownView from '@/components/common/MarkdownView.vue'
import SearchBox from '@/components/common/SearchBox.vue'
import { countHits, escapeRe, matchAll, snippets, stripMd, terms } from '@/utils/search'
import PageHero from '@/components/common/PageHero.vue'
import { CATEGORIES, CHAPTERS, TOTAL_MINUTES } from '@/tutorial'

const route = useRoute()
const router = useRouter()
const CAT_ICONS: Record<string, any> = { start: Compass, basics: Sprout, practice: Wrench, advanced: Rocket, teacher: Presentation }

// 学习进度只是本机的阅读记录，存在浏览器里；读不到时当作全部未读
const KEY = 'learn-progress'
function loadDone(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')) } catch { return new Set() }
}
const done = ref(loadDone())
function save() {
  try { localStorage.setItem(KEY, JSON.stringify([...done.value])) } catch { /* 隐私模式等不可写时忽略 */ }
}
function toggle(id: string) {
  const s = new Set(done.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  done.value = s
  save()
}

const chapter = computed(() => CHAPTERS.find((c) => c.id === route.params.id) ?? null)
const prev = computed(() => (chapter.value ? CHAPTERS[chapter.value.index - 2] ?? null : null))
const next = computed(() => (chapter.value ? CHAPTERS[chapter.value.index] ?? null : null))
const doneCount = computed(() => CHAPTERS.filter((c) => done.value.has(c.id)).length)
const percent = computed(() => Math.round((doneCount.value / CHAPTERS.length) * 100))
const resume = computed(() => CHAPTERS.find((c) => !done.value.has(c.id)) ?? CHAPTERS[0])
const tocOpen = ref(false)

// ---------------- 沉浸式阅读：收起目录、字号、全屏（偏好记在本机浏览器）
function pref(key: string, def: string) { try { return localStorage.getItem(key) ?? def } catch { return def } }
function setPref(key: string, v: string) { try { localStorage.setItem(key, v) } catch { /* 不可写时只在本次有效 */ } }
const tocCollapsed = ref(pref('learn-toc', 'open') === 'closed')
const SIZES = [14, 15, 16.5, 18, 20]
const sizeIdx = ref(Math.min(SIZES.length - 1, Math.max(0, Number(pref('learn-font', '1')) || 0)))
const readSize = computed(() => `${SIZES[sizeIdx.value]}px`)
const immersive = ref(false)
function toggleToc() { tocCollapsed.value = !tocCollapsed.value; setPref('learn-toc', tocCollapsed.value ? 'closed' : 'open') }
function font(d: number) { sizeIdx.value = Math.min(SIZES.length - 1, Math.max(0, sizeIdx.value + d)); setPref('learn-font', String(sizeIdx.value)) }
function setImmersive(on: boolean) {
  immersive.value = on
  document.documentElement.classList.toggle('learn-immersive', on)
}
async function toggleImmersive() {
  if (!immersive.value) {
    setImmersive(true)
    // 浏览器全屏；不支持或被拒绝时退化为页面内沉浸（隐藏侧边栏和目录）
    try { await document.documentElement.requestFullscreen?.() } catch { /* 页面内沉浸 */ }
  } else {
    setImmersive(false)
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => {})
  }
}
function onFsChange() { if (!document.fullscreenElement && immersive.value) setImmersive(false) }
function onKey(e: KeyboardEvent) {
  if (!chapter.value) return
  const typing = (e.target as HTMLElement)?.closest?.('input, textarea, [contenteditable]')
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return
  if (findCount.value && e.key === 'Enter') { e.preventDefault(); return goFind(findIdx.value + (e.shiftKey ? -1 : 1)) }
  if (findCount.value && e.key === 'Escape' && !immersive.value) return closeFind()
  if (e.key === 'Escape' && immersive.value && !document.fullscreenElement) setImmersive(false)
  else if (immersive.value && e.key === 'ArrowRight' && next.value) router.push(`/learn/${next.value.id}`)
  else if (immersive.value && e.key === 'ArrowLeft' && prev.value) router.push(`/learn/${prev.value.id}`)
}
onMounted(() => { document.addEventListener('fullscreenchange', onFsChange); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFsChange)
  window.removeEventListener('keydown', onKey)
  if (immersive.value) { setImmersive(false); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}) }
})
const minRange = (() => { const m = CHAPTERS.map((c) => c.minutes); return `${Math.min(...m)}~${Math.max(...m)}` })()

// ---------------- 搜索：目录页全文搜索；章节页目录筛选；从搜索结果进入章节时在正文中高亮并逐处定位
const PLAIN = new Map(CHAPTERS.map((c) => [c.id, stripMd(c.body)]))
const q = ref('')
const cursor = ref(0)
watch(q, () => (cursor.value = 0))
const results = computed(() => {
  const ts = terms(q.value)
  if (!ts.length) return []
  return CHAPTERS.flatMap((c) => {
    const plain = PLAIN.get(c.id)!
    if (!matchAll(`${c.title} ${c.summary} ${plain}`, ts)) return []
    const n = countHits(plain, q.value)
    return [{ c, n, snips: snippets(plain, q.value, 2), score: countHits(c.title, q.value) * 20 + countHits(c.summary, q.value) * 8 + n }]
  }).sort((a, b) => b.score - a.score)
})
function moveCursor(d: number) {
  const n = results.value.length
  if (!n) return
  cursor.value = (cursor.value + d + n) % n
  document.querySelector(`.res[data-i="${cursor.value}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}
function openResult() {
  const r = results.value[cursor.value]
  if (r) router.push({ path: `/learn/${r.c.id}`, query: { q: q.value.trim() } })
}
const SUGGEST = ['夏普比率', '最大回撤', '复权', '均线', 'ATR', '过拟合', '组合']

const tocQ = ref('')
const tocCats = computed(() => {
  const ts = terms(tocQ.value)
  if (!ts.length) return CATEGORIES
  return CATEGORIES.map((c) => ({ ...c, chapters: c.chapters.filter((ch) => matchAll(`${ch.title} ${ch.summary} ${PLAIN.get(ch.id)}`, ts)) }))
    .filter((c) => c.chapters.length)
})
const chLink = (id: string) => (tocQ.value.trim() ? { path: `/learn/${id}`, query: { q: tocQ.value.trim() } } : `/learn/${id}`)

const findQ = computed(() => (typeof route.query.q === 'string' ? route.query.q : ''))
const findCount = ref(0)
const findIdx = ref(0)
let markEls: HTMLElement[] = []
function clearMarks() {
  for (const m of markEls) {
    const parent = m.parentNode
    if (!parent) continue
    parent.replaceChild(document.createTextNode(m.textContent ?? ''), m)
    parent.normalize()
  }
  markEls = []
  findCount.value = 0
}
async function waitFor(sel: string, ms = 1500): Promise<HTMLElement | null> {
  const end = Date.now() + ms
  while (Date.now() < end) {
    const el = document.querySelector<HTMLElement>(sel)
    if (el) return el
    await new Promise((r) => requestAnimationFrame(r))
  }
  return null
}
async function applyFind() {
  clearMarks()
  const ts = terms(findQ.value)
  const ch = chapter.value
  if (!ts.length || !ch) return
  const root = await waitFor(`.paper-wrap[data-ch="${ch.id}"] .paper`)
  if (!root || chapter.value?.id !== ch.id) return
  const src = ts.map(escapeRe).join('|')
  const test = new RegExp(src, 'i')
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => n.parentElement?.closest('mark, button, .ch-foot, .ch-meta') || !test.test(n.nodeValue ?? '')
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  })
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  for (const node of nodes) {
    const text = node.nodeValue ?? ''
    const frag = document.createDocumentFragment()
    let last = 0
    for (const m of text.matchAll(new RegExp(src, 'gi'))) {
      frag.append(text.slice(last, m.index))
      const mk = document.createElement('mark')
      mk.className = 'hl'
      mk.textContent = m[0]
      frag.append(mk)
      markEls.push(mk)
      last = m.index! + m[0].length
    }
    frag.append(text.slice(last))
    node.parentNode?.replaceChild(frag, node)
  }
  findCount.value = markEls.length
  if (markEls.length) window.setTimeout(() => goFind(0), 260) // 等切换章节时的回到顶部滚动结束
}
function goFind(i: number) {
  if (!markEls.length) return
  findIdx.value = (i + markEls.length) % markEls.length
  markEls.forEach((m) => m.classList.remove('hl-cur'))
  const m = markEls[findIdx.value]
  m.closest('details')?.setAttribute('open', '') // 自测题答案默认折叠，命中时展开
  void m.offsetWidth
  m.classList.add('hl-cur')
  m.scrollIntoView({ block: 'center', behavior: 'smooth' })
}
function closeFind() {
  clearMarks()
  const { q: _q, ...rest } = route.query
  router.replace({ query: rest })
}
watch([() => chapter.value?.id, findQ], () => applyFind())
onMounted(() => applyFind())

function finish() {
  if (!chapter.value) return
  if (!done.value.has(chapter.value.id)) toggle(chapter.value.id)
  if (next.value) router.push(`/learn/${next.value.id}`)
}

watch(() => route.params.id, async () => {
  tocOpen.value = false
  await nextTick()
  document.querySelector('.main')?.scrollTo({ top: 0, behavior: 'smooth' })
})
</script>

<template>
  <Transition name="learn-swap" mode="out-in">
  <!-- 目录页 -->
  <div v-if="!chapter" key="home" class="page learn">
    <PageHero title="新手教程" tone="amber" :icon="GraduationCap"
      desc="写给零基础同学的量化入门笔记：从「什么是量化」讲起，一步一步学会看懂回测、调参数、做组合，直到熟练使用整个平台。">
      <template #actions>
        <NButton type="primary" size="large" @click="router.push(`/learn/${resume.id}`)">
          <template #icon><BookOpenCheck :size="17" /></template>{{ doneCount ? '继续学习' : '从第一章开始' }}
        </NButton>
      </template>
      <div class="hero-stats">
        <div class="hero-stat"><span class="ic-tile tone-amber"><ListTree :size="16" /></span><div><div class="v">{{ CHAPTERS.length }} 章</div><div class="l">{{ CATEGORIES.length }} 个分类</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-teal"><Clock :size="16" /></span><div><div class="v">约 {{ TOTAL_MINUTES }} 分钟</div><div class="l">每章 {{ minRange }} 分钟</div></div></div>
        <div class="hero-stat progress-stat">
          <span class="ic-tile tone-violet"><Check :size="16" /></span>
          <div class="grow"><div class="v">{{ doneCount }} / {{ CHAPTERS.length }}</div>
            <NProgress type="line" :percentage="percent" :show-indicator="false" :height="6" :border-radius="6" color="var(--t-violet)" rail-color="var(--surface-3)" /></div>
        </div>
      </div>
    </PageHero>

    <div class="lsearch">
      <SearchBox v-model="q" hotkey :placeholder="`搜索全部 ${CHAPTERS.length} 章的标题和正文，如 夏普比率、复权、ATR`" :count="q.trim() ? results.length : null"
                 @move="moveCursor" @enter="openResult" />
      <div v-if="!q.trim()" class="lsearch-sug">
        <span>常搜：</span><button v-for="w in SUGGEST" :key="w" @click="q = w">{{ w }}</button>
      </div>
      <div v-else class="lsearch-sug"><span>↑ ↓ 选择 · 回车打开 · Esc 清空</span></div>
    </div>

    <Transition name="learn-swap" mode="out-in">
    <div v-if="q.trim()" key="res" class="results">
      <RouterLink v-for="(r, i) in results" :key="r.c.id" :data-i="i" :to="{ path: `/learn/${r.c.id}`, query: { q: q.trim() } }"
                  class="res" :class="[`tone-${r.c.category.tone}`, { cur: i === cursor }]" :style="{ animationDelay: `${Math.min(i, 10) * 35}ms` }"
                  @mouseenter="cursor = i">
        <span class="res-no" :class="{ done: done.has(r.c.id) }"><Check v-if="done.has(r.c.id)" :size="13" :stroke-width="3" /><template v-else>{{ r.c.index }}</template></span>
        <div class="res-main">
          <div class="res-meta">
            <span class="res-cat"><component :is="CAT_ICONS[r.c.category.key]" :size="12" /> {{ r.c.category.title }}</span>
            <span><Clock :size="12" /> {{ r.c.minutes }} 分钟</span>
            <span v-if="r.n" class="res-n">正文 {{ r.n }} 处</span>
          </div>
          <h3><HighlightText :text="r.c.title" :q="q" /></h3>
          <p class="res-sum"><HighlightText :text="r.c.summary" :q="q" /></p>
          <p v-for="(sn, k) in r.snips" :key="k" class="res-snip"><HighlightText :text="sn" :q="q" /></p>
        </div>
        <ArrowRight class="res-go" :size="18" />
      </RouterLink>
      <div v-if="!results.length" class="res-empty">
        <span class="res-empty-ic"><SearchX :size="24" /></span>
        <b>没有找到包含「{{ q.trim() }}」的章节</b>
        <span>换个说法试试：</span>
        <div class="lsearch-sug center"><button v-for="w in SUGGEST" :key="w" @click="q = w">{{ w }}</button></div>
      </div>
    </div>
    <div v-else key="cats" class="cats stagger">
      <section v-for="(c, ci) in CATEGORIES" :key="c.key" class="cat notebook" :class="`tone-${c.tone}`">
        <header class="cat-head">
          <span class="cat-ic"><component :is="CAT_ICONS[c.key]" :size="20" /></span>
          <div>
            <div class="cat-step">第 {{ ci + 1 }} 部分</div>
            <h2>{{ c.title }}</h2>
            <p>{{ c.desc }}</p>
          </div>
          <span class="cat-count">{{ c.chapters.filter((x) => done.has(x.id)).length }}/{{ c.chapters.length }}</span>
        </header>
        <ol class="cat-list">
          <li v-for="ch in c.chapters" :key="ch.id">
            <RouterLink :to="`/learn/${ch.id}`" class="cat-item" :class="{ done: done.has(ch.id) }">
              <span class="no"><Check v-if="done.has(ch.id)" :size="13" :stroke-width="3" /><template v-else>{{ ch.index }}</template></span>
              <span class="txt"><b>{{ ch.title }}</b><em>{{ ch.summary }}</em></span>
              <span class="min">{{ ch.minutes }} 分钟</span>
            </RouterLink>
          </li>
        </ol>
      </section>
    </div>
    </Transition>
  </div>

  <!-- 章节页 -->
  <div v-else key="reading" class="page learn reading" :class="{ collapsed: tocCollapsed, immersive }">
    <aside class="toc" :class="{ open: tocOpen }">
      <button class="toc-toggle" @click="tocOpen = !tocOpen">
        <ListTree :size="16" /> 目录 · 第 {{ chapter.index }} / {{ CHAPTERS.length }} 章
        <ChevronDown :size="16" class="chev" />
      </button>
      <div class="toc-body">
        <RouterLink to="/learn" class="toc-home"><ArrowLeft :size="14" /> 教程首页</RouterLink>
        <div class="toc-progress">
          <span>学习进度 {{ percent }}%</span>
          <NProgress type="line" :percentage="percent" :show-indicator="false" :height="5" :border-radius="5" color="var(--t-amber)" rail-color="var(--surface-3)" />
        </div>
        <SearchBox v-model="tocQ" size="sm" class="toc-search" placeholder="筛选章节（含正文）" :count="tocQ.trim() ? tocCats.reduce((n, c) => n + c.chapters.length, 0) : null" />
        <TransitionGroup name="toc-f">
        <div v-for="c in tocCats" :key="c.key" class="toc-cat" :class="`tone-${c.tone}`">
          <div class="toc-cat-title"><component :is="CAT_ICONS[c.key]" :size="14" /> {{ c.title }}</div>
          <TransitionGroup name="toc-f">
          <RouterLink v-for="ch in c.chapters" :key="ch.id" :to="chLink(ch.id)" class="toc-item"
            :class="{ active: ch.id === chapter.id, done: done.has(ch.id) }">
            <span class="dot"><Check v-if="done.has(ch.id)" :size="11" :stroke-width="3.2" /><template v-else>{{ ch.index }}</template></span>
            <span class="t"><HighlightText :text="ch.title" :q="tocQ" /></span>
          </RouterLink>
          </TransitionGroup>
        </div>
        </TransitionGroup>
        <div v-if="!tocCats.length" class="toc-none">没有匹配的章节</div>
      </div>
    </aside>

    <div class="col">
    <div class="read-bar">
      <button class="rb" :title="tocCollapsed ? '展开目录' : '收起目录'" @click="toggleToc">
        <PanelLeftOpen v-if="tocCollapsed" :size="16" /><PanelLeftClose v-else :size="16" />
        <span>{{ tocCollapsed ? '展开目录' : '收起目录' }}</span>
      </button>
      <span class="rb-info">第 {{ chapter.index }} / {{ CHAPTERS.length }} 章 · {{ chapter.category.title }}</span>
      <Transition name="find">
        <div v-if="findQ" class="find" :class="{ none: !findCount }">
          <Search :size="14" />
          <span class="find-q">{{ findQ }}</span>
          <span class="find-n">{{ findCount ? `${findIdx + 1} / ${findCount}` : '本章正文无匹配' }}</span>
          <button title="上一处（Shift+Enter）" :disabled="!findCount" @click="goFind(findIdx - 1)"><ChevronUp :size="15" /></button>
          <button title="下一处（Enter）" :disabled="!findCount" @click="goFind(findIdx + 1)"><ChevronDown :size="15" /></button>
          <button title="关闭（Esc）" @click="closeFind"><X :size="14" /></button>
        </div>
      </Transition>
      <div class="rb-group">
        <button class="rb icon" title="缩小字号" :disabled="sizeIdx === 0" @click="font(-1)"><AArrowDown :size="17" /></button>
        <span class="rb-size">{{ SIZES[sizeIdx] }}</span>
        <button class="rb icon" title="放大字号" :disabled="sizeIdx === SIZES.length - 1" @click="font(1)"><AArrowUp :size="17" /></button>
      </div>
      <button class="rb primary" :title="immersive ? '退出全屏（Esc）' : '全屏沉浸阅读'" @click="toggleImmersive">
        <Minimize v-if="immersive" :size="16" /><Maximize v-else :size="16" />
        <span>{{ immersive ? '退出全屏' : '全屏阅读' }}</span>
      </button>
    </div>
    <Transition name="page-turn" mode="out-in">
    <article :key="chapter.id" :data-ch="chapter.id" class="paper-wrap" :style="{ '--read-size': readSize }">
      <div class="notebook paper" :class="`tone-${chapter.category.tone}`">
        <header class="ch-head">
          <div class="ch-meta">
            <span class="ch-cat"><component :is="CAT_ICONS[chapter.category.key]" :size="13" /> {{ chapter.category.title }}</span>
            <span>第 {{ chapter.index }} 章</span>
            <span><Clock :size="13" /> 约 {{ chapter.minutes }} 分钟</span>
            <span v-if="done.has(chapter.id)" class="ch-done"><Check :size="13" /> 已学完</span>
          </div>
          <h1>{{ chapter.title }}</h1>
          <p>{{ chapter.summary }}</p>
        </header>
        <MarkdownView :source="chapter.body" />
        <footer class="ch-foot">
          <NButton v-if="!done.has(chapter.id)" type="primary" size="large" @click="finish">
            <template #icon><Check :size="17" /></template>我学会了{{ next ? '，下一章' : '' }}
          </NButton>
          <NButton v-else secondary size="large" @click="toggle(chapter.id)">标记为未学完</NButton>
        </footer>
      </div>

      <nav class="pager">
        <RouterLink v-if="prev" :to="`/learn/${prev.id}`" class="pg prev">
          <ArrowLeft :size="16" /><span><em>上一章</em><b>{{ prev.title }}</b></span>
        </RouterLink>
        <span v-else />
        <RouterLink v-if="next" :to="`/learn/${next.id}`" class="pg next">
          <span><em>下一章</em><b>{{ next.title }}</b></span><ArrowRight :size="16" />
        </RouterLink>
        <RouterLink v-else to="/learn" class="pg next">
          <span><em>全部读完啦</em><b>回到教程首页</b></span><ArrowRight :size="16" />
        </RouterLink>
      </nav>
    </article>
    </Transition>
    </div>
    <!-- 全屏时的悬浮导航 -->
    <Transition name="learn-swap">
      <div v-if="immersive" class="float-nav">
        <button :disabled="!prev" title="上一章（←）" @click="prev && router.push(`/learn/${prev.id}`)"><ArrowLeft :size="16" /></button>
        <span>{{ chapter.index }} / {{ CHAPTERS.length }}</span>
        <button :disabled="!next" title="下一章（→）" @click="next && router.push(`/learn/${next.id}`)"><ArrowRight :size="16" /></button>
        <i />
        <button title="缩小字号" :disabled="sizeIdx === 0" @click="font(-1)"><AArrowDown :size="16" /></button>
        <button title="放大字号" :disabled="sizeIdx === SIZES.length - 1" @click="font(1)"><AArrowUp :size="16" /></button>
        <i />
        <button title="退出全屏（Esc）" @click="toggleImmersive"><Minimize :size="16" /></button>
      </div>
    </Transition>
  </div>
  </Transition>
</template>

<style scoped>
/* ---------- 目录页 ---------- */
.progress-stat .grow { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.cats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.cat { padding: 22px 22px 18px 70px; }
.cat-head { display: flex; gap: 14px; align-items: flex-start; margin-bottom: 12px; }
.cat-ic {
  width: 42px; height: 42px; flex-shrink: 0; border-radius: 12px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(140deg, color-mix(in srgb, var(--tone) 70%, #fff), var(--tone));
  box-shadow: 0 6px 16px color-mix(in srgb, var(--tone) 35%, transparent); transform: rotate(-4deg);
}
.cat-step { font-size: 12px; font-weight: 650; color: var(--tone); letter-spacing: 1px; }
.cat-head h2 { margin: 0; font-size: 18px; font-weight: 700; }
.cat-head p { margin: 2px 0 0; font-size: 13px; color: var(--text-2); }
.cat-count { margin-left: auto; font-size: 12px; font-weight: 650; padding: 2px 10px; border-radius: 999px; color: var(--tone); background: var(--tone-soft); white-space: nowrap; }
.cat-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.cat-item {
  display: flex; align-items: center; gap: 12px; padding: 9px 10px; border-radius: 10px; color: var(--text-1);
  transition: background 0.2s, transform 0.25s var(--ease-out);
}
.cat-item:hover { background: color-mix(in srgb, var(--tone-soft) 80%, var(--surface)); transform: translateX(4px); }
.no {
  width: 26px; height: 26px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center; font-size: 12.5px; font-weight: 700;
  color: var(--tone); border: 1.5px dashed color-mix(in srgb, var(--tone) 60%, transparent); background: var(--paper);
}
.cat-item.done .no { color: #fff; background: var(--tone); border-style: solid; border-color: var(--tone); }
.txt { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.4; }
.txt b { font-size: 14px; font-weight: 600; }
.txt em { font-style: normal; font-size: 12px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.min { font-size: 12px; color: var(--text-3); white-space: nowrap; }

/* ---------- 搜索 ---------- */
.lsearch { max-width: 720px; margin: 0 auto 22px; }
.lsearch :deep(.sbox) { height: 46px; border-radius: 14px; box-shadow: var(--shadow-sm); }
.lsearch :deep(.sbox.focused) { box-shadow: 0 0 0 4px var(--primary-soft), var(--shadow-md); }
.lsearch :deep(input) { font-size: 14.5px; }
.lsearch-sug { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 10px; font-size: 12px; color: var(--text-3); }
.lsearch-sug.center { justify-content: center; margin-top: 0; }
.lsearch-sug button {
  border: 1px dashed var(--border-strong); background: var(--surface); color: var(--text-2); border-radius: 999px; padding: 2px 10px; font-size: 12px; cursor: pointer;
  transition: all 0.2s var(--ease-out);
}
.lsearch-sug button:hover { border-style: solid; border-color: var(--primary); color: var(--primary-ink); transform: translateY(-2px); }
.results { max-width: 880px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.res {
  position: relative; display: flex; gap: 14px; align-items: flex-start; padding: 16px 18px; border-radius: 14px; color: var(--text-1);
  background: var(--surface); border: 1px solid var(--border); animation: rise 0.35s var(--ease-out) both;
  transition: border-color 0.2s, box-shadow 0.25s, transform 0.25s var(--ease-out);
}
.res::before { content: ''; position: absolute; left: 0; top: 14px; bottom: 14px; width: 3px; border-radius: 3px; background: var(--tone); transform: scaleY(0); transition: transform 0.25s var(--ease-out); }
.res.cur { border-color: color-mix(in srgb, var(--tone) 55%, var(--border)); box-shadow: var(--shadow-md); transform: translateX(4px); }
.res.cur::before { transform: scaleY(1); }
.res-no {
  width: 30px; height: 30px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center; font-size: 13px; font-weight: 700;
  color: var(--tone); background: var(--tone-soft); transition: transform 0.3s var(--ease-spring);
}
.res-no.done { color: #fff; background: var(--tone); }
.res.cur .res-no { transform: scale(1.1) rotate(-8deg); }
.res-main { flex: 1; min-width: 0; }
.res-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--text-3); }
.res-meta > span { display: inline-flex; align-items: center; gap: 4px; }
.res-cat { color: var(--tone); font-weight: 600; }
.res-n { color: var(--primary-ink); }
.res h3 { margin: 4px 0 2px; font-size: 16px; font-weight: 650; }
.res-sum { margin: 0; font-size: 13px; color: var(--text-2); }
.res-snip { margin: 6px 0 0; padding: 6px 10px; border-radius: 8px; font-size: 12.5px; line-height: 1.6; color: var(--text-2); background: var(--surface-2); border-left: 2px solid color-mix(in srgb, var(--tone) 40%, transparent); }
.res-go { flex-shrink: 0; align-self: center; color: var(--text-3); transition: transform 0.25s var(--ease-out), color 0.2s; }
.res.cur .res-go { color: var(--tone); transform: translateX(4px); }
.res-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 48px 16px; color: var(--text-3); font-size: 13px; animation: rise 0.4s var(--ease-out) both; }
.res-empty b { font-size: 15px; color: var(--text-1); }
.res-empty-ic { width: 54px; height: 54px; border-radius: 16px; display: grid; place-items: center; background: var(--warn-soft); color: var(--warn); animation: wobble 2.6s ease-in-out infinite; }
@keyframes wobble { 25% { transform: rotate(-8deg); } 75% { transform: rotate(8deg); } }
.toc-search { margin-bottom: 14px; }
.toc-none { font-size: 12.5px; color: var(--text-3); text-align: center; padding: 12px 0; }
.toc-f-enter-active, .toc-f-leave-active { transition: opacity 0.2s, transform 0.25s var(--ease-out); }
.toc-f-enter-from, .toc-f-leave-to { opacity: 0; transform: translateX(-10px); }
.find {
  display: inline-flex; align-items: center; gap: 4px; height: 32px; padding: 0 4px 0 10px; border-radius: 9px; font-size: 12.5px;
  color: var(--text-2); background: color-mix(in srgb, #f5b301 12%, var(--surface)); border: 1px solid color-mix(in srgb, #f5b301 45%, var(--border));
}
.find.none { background: var(--surface); border-color: var(--border); }
.find-q { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 650; color: var(--text-1); }
.find-n { min-width: 46px; text-align: center; font-variant-numeric: tabular-nums; color: var(--text-3); }
.find button { width: 26px; height: 26px; border: none; background: none; border-radius: 7px; display: grid; place-items: center; cursor: pointer; color: var(--text-2); }
.find button:hover:not(:disabled) { background: var(--surface-3); color: var(--text-1); }
.find button:disabled { opacity: 0.35; cursor: default; }
.find-enter-active { transition: opacity 0.25s, transform 0.3s var(--ease-spring); }
.find-leave-active { transition: opacity 0.15s, transform 0.15s; }
.find-enter-from, .find-leave-to { opacity: 0; transform: translateY(-6px) scale(0.95); }

/* ---------- 章节页 ---------- */
.reading { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 24px; align-items: start; max-width: 1240px;
  transition: grid-template-columns 0.35s var(--ease-out), gap 0.35s var(--ease-out), max-width 0.35s var(--ease-out); }
.toc { position: sticky; top: 20px; max-height: calc(100vh - 40px); overflow-y: auto; padding-right: 4px;
  transition: opacity 0.25s ease, transform 0.35s var(--ease-out); }
/* 收起目录：目录列宽度收为 0，正文居中加宽 */
.reading.collapsed { grid-template-columns: 0 minmax(0, 1fr); gap: 0; max-width: 1060px; }
.reading.collapsed .toc { opacity: 0; transform: translateX(-16px); pointer-events: none; overflow: hidden; }
.col { min-width: 0; }
.read-bar {
  position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 10px; margin: -6px 0 12px; padding: 8px 0;
  background: linear-gradient(var(--bg) 70%, transparent);
}
.rb {
  display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: 9px; cursor: pointer;
  font: inherit; font-size: 13px; color: var(--text-2); background: var(--surface); border: 1px solid var(--border);
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.rb:hover:not(:disabled) { color: var(--text-1); border-color: var(--border-strong); background: var(--surface-2); }
.rb:disabled { opacity: 0.4; cursor: default; }
.rb.icon { width: 32px; padding: 0; justify-content: center; border: 0; background: none; }
.rb.primary { color: var(--primary-ink); border-color: color-mix(in srgb, var(--primary) 35%, var(--border)); background: var(--primary-soft); }
.rb-info { flex: 1; min-width: 0; font-size: 12.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rb-group { display: inline-flex; align-items: center; padding: 0 2px; border-radius: 9px; background: var(--surface); border: 1px solid var(--border); }
.rb-size { min-width: 26px; text-align: center; font-size: 12px; color: var(--text-3); font-variant-numeric: tabular-nums; }
/* 全屏沉浸：隐藏目录，正文居中，底部悬浮导航 */
.reading.immersive { grid-template-columns: 0 minmax(0, 1fr); gap: 0; max-width: 1000px; padding-top: 28px; padding-bottom: 90px; }
.reading.immersive .toc { opacity: 0; pointer-events: none; overflow: hidden; }
.reading.immersive .read-bar, .reading.immersive .pager { display: none; }
.float-nav {
  position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 50; display: flex; align-items: center; gap: 2px;
  padding: 6px 8px; border-radius: 999px; background: color-mix(in srgb, var(--surface) 88%, transparent); backdrop-filter: blur(10px);
  border: 1px solid var(--border); box-shadow: 0 12px 32px rgba(16, 24, 40, 0.22); opacity: 0.55; transition: opacity 0.25s;
}
.float-nav:hover { opacity: 1; }
.float-nav button {
  width: 34px; height: 34px; border: 0; border-radius: 50%; display: grid; place-items: center; cursor: pointer;
  color: var(--text-1); background: none; transition: background 0.15s;
}
.float-nav button:hover:not(:disabled) { background: var(--surface-3); }
.float-nav button:disabled { opacity: 0.35; cursor: default; }
.float-nav span { min-width: 54px; text-align: center; font-size: 12.5px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.float-nav i { width: 1px; height: 18px; margin: 0 4px; background: var(--border-strong); }
.toc-toggle { display: none; }
.toc-home { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: var(--text-3); margin-bottom: 12px; }
.toc-home:hover { color: var(--primary); }
.toc-progress { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-2); margin-bottom: 16px; padding: 10px 12px; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); }
.toc-cat { margin-bottom: 14px; }
.toc-cat-title { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 700; color: var(--tone); margin: 0 0 4px 4px; letter-spacing: 0.5px; }
.toc-item {
  position: relative; display: flex; align-items: center; gap: 9px; padding: 6px 8px; border-radius: 8px;
  font-size: 13px; color: var(--text-2); line-height: 1.4; transition: background 0.15s, color 0.15s;
}
.toc-item:hover { background: var(--surface-3); color: var(--text-1); }
.toc-item.active { background: var(--tone-soft); color: var(--text-1); font-weight: 600; }
.toc-item.active::before { content: ""; position: absolute; left: -2px; top: 7px; bottom: 7px; width: 3px; border-radius: 3px; background: var(--tone); }
.dot {
  width: 20px; height: 20px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center;
  font-size: 11px; font-weight: 700; color: var(--tone); background: var(--tone-soft);
}
.toc-item.done .dot { color: #fff; background: var(--tone); }
.t { overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }

.paper-wrap { min-width: 0; }
.reading > .paper-wrap { animation: none; } /* 由 page-turn 过渡负责，不再叠加全局入场动画 */
/* 章节之间：旧页向左淡出、新页从右侧滑入，像翻笔记本 */
.page-turn-enter-active { transition: opacity 0.32s var(--ease-out), transform 0.32s var(--ease-out); }
.page-turn-leave-active { transition: opacity 0.16s ease, transform 0.16s ease; }
.page-turn-enter-from { opacity: 0; transform: translateX(18px); }
.page-turn-leave-to { opacity: 0; transform: translateX(-10px); }
.learn-swap-enter-active { transition: opacity 0.3s var(--ease-out), transform 0.3s var(--ease-out); }
.learn-swap-leave-active { transition: opacity 0.14s ease; }
.learn-swap-enter-from { opacity: 0; transform: translateY(8px); }
.learn-swap-leave-to { opacity: 0; }
.paper { padding-top: 34px; padding-bottom: 30px; }
.ch-head { margin-bottom: 22px; padding-bottom: 18px; border-bottom: 2px solid color-mix(in srgb, var(--tone) 35%, transparent); }
.ch-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; font-size: 12.5px; color: var(--text-3); }
.ch-meta > span { display: inline-flex; align-items: center; gap: 4px; }
.ch-cat { padding: 2px 10px; border-radius: 999px; font-weight: 650; color: var(--tone); background: var(--tone-soft); }
.ch-done { color: var(--c-tip); font-weight: 600; }
.ch-head h1 { margin: 10px 0 4px; font-size: 27px; font-weight: 750; letter-spacing: 0.5px; color: var(--text-1); }
.ch-head p { margin: 0; font-size: 14px; color: var(--text-2); }
.ch-foot { margin-top: 30px; padding-top: 20px; border-top: 1px dashed var(--border-strong); display: flex; justify-content: center; }
.paper :deep(.md) { font-size: var(--read-size, 15px); }

.pager { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px; }
.pg {
  display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 12px; color: var(--text-1);
  background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-sm);
  transition: border-color 0.2s, transform 0.25s var(--ease-out), box-shadow 0.25s;
}
.pg:hover { border-color: color-mix(in srgb, var(--primary) 50%, var(--border)); transform: translateY(-2px); box-shadow: var(--shadow-md); }
.pg span { display: flex; flex-direction: column; min-width: 0; }
.pg em { font-style: normal; font-size: 12px; color: var(--text-3); }
.pg b { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pg.next { justify-content: flex-end; text-align: right; }
.pg svg { flex-shrink: 0; color: var(--primary); }

@media (max-width: 1000px) {
  .reading.collapsed, .reading.immersive { grid-template-columns: 1fr; }
  .read-bar .rb:first-child, .rb-info { display: none; }
  .read-bar { justify-content: flex-end; }
  .cats { grid-template-columns: 1fr; }
  .reading { grid-template-columns: 1fr; }
  .toc { position: static; max-height: none; }
  .toc-toggle {
    display: flex; width: 100%; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 12px; cursor: pointer;
    font: inherit; font-size: 13.5px; font-weight: 600; color: var(--text-1); background: var(--surface); border: 1px solid var(--border);
  }
  .toc-toggle .chev { margin-left: auto; transition: transform 0.25s; }
  .toc.open .chev { transform: rotate(180deg); }
  .toc-body { display: none; margin-top: 10px; }
  .toc.open .toc-body { display: block; }
}
@media (max-width: 640px) {
  .cat { padding: 18px 14px 14px 30px; }
  .min { display: none; }
  .ch-head h1 { font-size: 22px; }
  .pager { grid-template-columns: 1fr; }
}
</style>
