// 数字格式化：比例类以百分数显示，比率保留两位小数
export function pct(v: number | null | undefined, digits = 1, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const s = (v * 100).toFixed(digits) + '%'
  return signed && v > 0 ? '+' + s : s
}

export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  if (!Number.isFinite(v)) return '∞'
  return v.toFixed(digits)
}

export function money(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e8) return (v / 1e8).toFixed(2) + ' 亿'
  if (a >= 1e4) return (v / 1e4).toFixed(2) + ' 万'
  return v.toFixed(0)
}

export function int(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return Math.round(v).toLocaleString('zh-CN')
}

/** 收益类数字的涨跌色：A 股红涨绿跌 */
export function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return ''
  return v > 0 ? 'up' : 'down'
}

export function paramValue(v: unknown): string {
  if (typeof v === 'boolean') return v ? '开启' : '关闭'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(+v.toFixed(4))
  return String(v)
}

export const UNIVERSE_LABELS: Record<string, string> = {
  stock_pool: '教学股票池',
  industries: '申万一级行业',
  futures: '商品期货主力合约',
}

export function universeLabel(u: string | undefined): string {
  if (!u) return ''
  if (UNIVERSE_LABELS[u]) return UNIVERSE_LABELS[u]
  const n = u.split(',').filter(Boolean).length
  return n === 1 ? u : `${n} 个指定标的`
}

export function timeAgo(iso: string): string {
  const t = new Date(iso).getTime()
  const d = (Date.now() - t) / 1000
  if (d < 60) return '刚刚'
  if (d < 3600) return `${Math.floor(d / 60)} 分钟前`
  if (d < 86400) return `${Math.floor(d / 3600)} 小时前`
  if (d < 86400 * 7) return `${Math.floor(d / 86400)} 天前`
  return iso.slice(0, 10)
}
