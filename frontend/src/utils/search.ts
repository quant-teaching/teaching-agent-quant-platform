// 页面内搜索的小工具：关键词拆分、命中分段（用于高亮）、Markdown 去符号、取命中片段

/** 按空格拆成多个关键词，全部转小写；空串返回 [] */
export function terms(q: string): string[] {
  return q.trim().toLowerCase().split(/\s+/).filter(Boolean)
}

/** 转义正则特殊字符 */
export const escapeRe = (k: string) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** 文本是否包含全部关键词（不区分大小写） */
export function matchAll(text: string, ts: string[]): boolean {
  const t = text.toLowerCase()
  return ts.every((k) => t.includes(k))
}

/** 把文本切成「命中 / 未命中」片段，供高亮显示 */
export function splitHits(text: string, q: string): { t: string; hit: boolean }[] {
  const ts = terms(q)
  if (!text || !ts.length) return [{ t: text ?? '', hit: false }]
  const re = new RegExp(`(${ts.map(escapeRe).join('|')})`, 'gi')
  return text.split(re).filter((x) => x !== '').map((x) => ({ t: x, hit: ts.includes(x.toLowerCase()) }))
}

/** 去掉 Markdown 标记，得到便于检索和摘录的纯文本 */
export function stripMd(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^>\s*\[![A-Z]+\]\s*/gm, '')
    .replace(/[#>*`|_~]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** 在长文本里找出最多 max 处命中，每处前后各留一些上下文 */
export function snippets(text: string, q: string, max = 2, before = 18, after = 46): string[] {
  const ts = terms(q)
  if (!ts.length) return []
  const low = text.toLowerCase()
  const out: string[] = []
  let from = 0
  while (out.length < max) {
    let i = -1, len = 0
    for (const k of ts) {
      const j = low.indexOf(k, from)
      if (j >= 0 && (i < 0 || j < i)) { i = j; len = k.length }
    }
    if (i < 0) break
    const a = Math.max(0, i - before), b = Math.min(text.length, i + len + after)
    out.push((a ? '…' : '') + text.slice(a, b) + (b < text.length ? '…' : ''))
    from = b
  }
  return out
}

/** 统计文本中关键词出现的次数 */
export function countHits(text: string, q: string): number {
  const low = text.toLowerCase()
  return terms(q).reduce((n, k) => n + (low.split(k).length - 1), 0)
}
