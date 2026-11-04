<script setup lang="ts">
// Markdown 渲染：教学文档、新手教程和智能体回复共用。
// - markdown-it-cjk-friendly：修复中文标点紧挨 ** 时加粗不生效（如「**问题：**回撤较深」）
// - > [!TIP] / [!NOTE] / [!WARNING] / [!KEY]：渲染成带图标的提示框
// - 单独一行的【优化建议】：渲染成小节标签；行首「问题：」「调整：」这类加粗：渲染成键名标签
// - 站内链接（/library 等）在当前页跳转，外部链接新窗口打开
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import MarkdownIt from 'markdown-it'
import cjkFriendly from 'markdown-it-cjk-friendly'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

hljs.registerLanguage('python', python)

const CALLOUTS: Record<string, string> = { TIP: '小贴士', NOTE: '说明', WARNING: '注意', KEY: '要点', TRY: '动手试试' }

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value
    return ''
  },
}).use(cjkFriendly)

md.core.ruler.push('teaching_blocks', (state) => {
  const tokens = state.tokens
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i]
    // 提示框：> [!TIP] 标题（标题可省略）
    if (t.type === 'blockquote_open' && tokens[i + 2]?.type === 'inline') {
      const inline = tokens[i + 2]
      const m = inline.content.match(/^\[!(TIP|NOTE|WARNING|KEY|TRY)\][ \t]*([^\n]*)\n?/)
      if (m) {
        t.attrJoin('class', `callout callout-${m[1].toLowerCase()}`)
        t.attrSet('data-label', m[2].trim() || CALLOUTS[m[1]])
        inline.content = inline.content.slice(m[0].length)
        const first = inline.children?.[0]
        if (first?.type === 'text') {
          first.content = first.content.replace(/^\[!(TIP|NOTE|WARNING|KEY|TRY)\][ \t]*[^\n]*/, '')
          if (inline.children![1]?.type === 'softbreak') inline.children!.splice(1, 1)
          if (!first.content) inline.children!.shift()
        }
        if (!inline.content.trim()) { // 只有标题没有正文的那一段整个去掉
          tokens.splice(i + 1, 3)
        }
      }
    }
    // 小节标签：整段只有【xxx】（可带加粗）
    if (t.type === 'paragraph_open' && tokens[i + 1]?.type === 'inline') {
      const m = tokens[i + 1].content.trim().match(/^\*{0,2}【([^】]{1,20})】\*{0,2}[:：]?$/)
      if (m) {
        t.attrJoin('class', 'md-label')
        tokens[i + 1].children = [Object.assign(new state.Token('text', '', 0), { content: m[1] })]
      }
    }
    // 键名标签：加粗内容以冒号结尾（问题：、调整：、原理：）
    if (t.type === 'inline' && t.children) {
      const ch = t.children
      for (let k = 0; k + 2 < ch.length; k++) {
        if (ch[k].type === 'strong_open' && ch[k + 1].type === 'text' && ch[k + 2].type === 'strong_close'
            && /^[^\s]{1,8}[:：]$/.test(ch[k + 1].content)) {
          ch[k].attrJoin('class', 'md-key')
          ch[k + 1].content = ch[k + 1].content.replace(/[:：]$/, '')
          // 键名前的换行保留为真正的换行，让「问题 / 调整 / 原理」各占一行
          if (k > 0 && ch[k - 1].type === 'softbreak') ch[k - 1].type = 'hardbreak'
        }
      }
    }
  }
})

// 外部链接新窗口打开；站内链接交给路由
const defaultRender = md.renderer.rules.link_open ?? ((tokens, idx, opts, _env, self) => self.renderToken(tokens, idx, opts))
md.renderer.rules.link_open = (tokens, idx, opts, env, self) => {
  const href = tokens[idx].attrGet('href') || ''
  if (href.startsWith('/')) tokens[idx].attrJoin('class', 'md-inlink')
  else {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noopener')
  }
  return defaultRender(tokens, idx, opts, env, self)
}
// 表格外包一层，窄屏横向滚动
md.renderer.rules.table_open = () => '<div class="md-table"><table>'
md.renderer.rules.table_close = () => '</table></div>'

// breaks：把单个换行也渲染成换行（智能体回复常用单换行分隔要点；教学文档按标准 Markdown 处理）
const props = defineProps<{ source: string; breaks?: boolean }>()
const html = computed(() => {
  md.set({ breaks: !!props.breaks })
  return md.render(props.source || '')
})
const router = useRouter()

function onClick(e: MouseEvent) {
  const a = (e.target as HTMLElement).closest('a.md-inlink') as HTMLAnchorElement | null
  if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return
  e.preventDefault()
  router.push(a.getAttribute('href')!)
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div class="md" @click="onClick" v-html="html" />
</template>
