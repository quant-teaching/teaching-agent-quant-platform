<script setup lang="ts">
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

hljs.registerLanguage('python', python)

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value
    return ''
  },
})
// 外部链接新窗口打开
const defaultRender = md.renderer.rules.link_open ?? ((tokens, idx, opts, _env, self) => self.renderToken(tokens, idx, opts))
md.renderer.rules.link_open = (tokens, idx, opts, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener')
  return defaultRender(tokens, idx, opts, env, self)
}

const props = defineProps<{ source: string }>()
const html = computed(() => md.render(props.source || ''))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div class="md" v-html="html" />
</template>
