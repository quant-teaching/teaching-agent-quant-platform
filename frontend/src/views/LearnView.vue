<script setup lang="ts">
// 新手教程：/learn 为目录页（按分类排列的章节卡片），/learn/:id 为章节页（左侧目录 + 格子纸正文 + 上下章）
import { ArrowLeft, ArrowRight, BookOpenCheck, Check, ChevronDown, Clock, Compass, GraduationCap, ListTree, Rocket, Sprout, Wrench } from 'lucide-vue-next'
import { NButton, NProgress } from 'naive-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarkdownView from '@/components/common/MarkdownView.vue'
import PageHero from '@/components/common/PageHero.vue'
import { CATEGORIES, CHAPTERS, TOTAL_MINUTES } from '@/tutorial'

const route = useRoute()
const router = useRouter()
const CAT_ICONS: Record<string, any> = { start: Compass, basics: Sprout, practice: Wrench, advanced: Rocket }

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
  <!-- 目录页 -->
  <div v-if="!chapter" class="page learn">
    <PageHero title="新手教程" tone="amber" :icon="GraduationCap"
      desc="写给零基础同学的量化入门笔记：从「什么是量化」讲起，一步一步学会看懂回测、调参数、做组合，直到熟练使用整个平台。">
      <template #actions>
        <NButton type="primary" size="large" @click="router.push(`/learn/${resume.id}`)">
          <template #icon><BookOpenCheck :size="17" /></template>{{ doneCount ? '继续学习' : '从第一章开始' }}
        </NButton>
      </template>
      <div class="hero-stats">
        <div class="hero-stat"><span class="ic-tile tone-amber"><ListTree :size="16" /></span><div><div class="v">{{ CHAPTERS.length }} 章</div><div class="l">{{ CATEGORIES.length }} 个分类</div></div></div>
        <div class="hero-stat"><span class="ic-tile tone-teal"><Clock :size="16" /></span><div><div class="v">约 {{ TOTAL_MINUTES }} 分钟</div><div class="l">每章 5~10 分钟</div></div></div>
        <div class="hero-stat progress-stat">
          <span class="ic-tile tone-violet"><Check :size="16" /></span>
          <div class="grow"><div class="v">{{ doneCount }} / {{ CHAPTERS.length }}</div>
            <NProgress type="line" :percentage="percent" :show-indicator="false" :height="6" :border-radius="6" color="var(--t-violet)" rail-color="var(--surface-3)" /></div>
        </div>
      </div>
    </PageHero>

    <div class="cats stagger">
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
  </div>

  <!-- 章节页 -->
  <div v-else class="page learn reading">
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
        <div v-for="c in CATEGORIES" :key="c.key" class="toc-cat" :class="`tone-${c.tone}`">
          <div class="toc-cat-title"><component :is="CAT_ICONS[c.key]" :size="14" /> {{ c.title }}</div>
          <RouterLink v-for="ch in c.chapters" :key="ch.id" :to="`/learn/${ch.id}`" class="toc-item"
            :class="{ active: ch.id === chapter.id, done: done.has(ch.id) }">
            <span class="dot"><Check v-if="done.has(ch.id)" :size="11" :stroke-width="3.2" /><template v-else>{{ ch.index }}</template></span>
            <span class="t">{{ ch.title }}</span>
          </RouterLink>
        </div>
      </div>
    </aside>

    <article :key="chapter.id" class="paper-wrap">
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
  </div>
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

/* ---------- 章节页 ---------- */
.reading { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 24px; align-items: start; max-width: 1240px; }
.toc { position: sticky; top: 20px; max-height: calc(100vh - 40px); overflow-y: auto; padding-right: 4px; }
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

.paper-wrap { min-width: 0; animation: rise 0.45s var(--ease-out) both; }
.paper { padding-top: 34px; padding-bottom: 30px; }
.ch-head { margin-bottom: 22px; padding-bottom: 18px; border-bottom: 2px solid color-mix(in srgb, var(--tone) 35%, transparent); }
.ch-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; font-size: 12.5px; color: var(--text-3); }
.ch-meta > span { display: inline-flex; align-items: center; gap: 4px; }
.ch-cat { padding: 2px 10px; border-radius: 999px; font-weight: 650; color: var(--tone); background: var(--tone-soft); }
.ch-done { color: var(--c-tip); font-weight: 600; }
.ch-head h1 { margin: 10px 0 4px; font-size: 27px; font-weight: 750; letter-spacing: 0.5px; color: var(--text-1); }
.ch-head p { margin: 0; font-size: 14px; color: var(--text-2); }
.ch-foot { margin-top: 30px; padding-top: 20px; border-top: 1px dashed var(--border-strong); display: flex; justify-content: center; }
.paper :deep(.md) { font-size: 15px; }

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
