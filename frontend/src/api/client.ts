// 后端接口。开发时通过 Vite 代理转发到 127.0.0.1:8000
export class ApiError extends Error {
  constructor(message: string, public status = 0) {
    super(message)
  }
}

// 登录过期时由 main.ts 注册的回调跳转到登录页
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}
export function handleUnauthorized(url: string) {
  if (!url.startsWith('/api/auth/')) onUnauthorized?.()
}

// 未开启登录、但设置了管理员密码时，修改模型设置需要带上它（本页会话内有效）
export const ADMIN_PW_KEY = 'admin-password'
function adminHeader(url: string): Record<string, string> {
  if (!url.startsWith('/api/llm/')) return {}
  try {
    const pw = sessionStorage.getItem(ADMIN_PW_KEY)
    return pw ? { 'X-Admin-Password': pw } : {}
  } catch {
    return {}
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const resp = await fetch(url, {
    method,
    headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...adminHeader(url) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await resp.text()
  let data: any = null
  try {
    data = text ? JSON.parse(text) : null
  } catch { /* 非 JSON（如网关错误页） */ }
  if (resp.status === 401) handleUnauthorized(url)
  if (!resp.ok) {
    const detail = data?.detail
    throw new ApiError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join('；') : `请求失败（${resp.status}）`, resp.status)
  }
  return data as T
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  put: <T>(url: string, body?: unknown) => request<T>('PUT', url, body ?? {}),
  patch: <T>(url: string, body?: unknown) => request<T>('PATCH', url, body ?? {}),
  del: <T>(url: string) => request<T>('DELETE', url),
}

// ---------------------------------------------------------------- 类型

export interface Holding {
  symbol: string
  name: string
  qty: number
  price: number
  value: number
  weight: number
  contract: string
  date?: string
}

export interface ParamSpec {
  key: string
  title: string
  type: string
  default: any
  description: string
  min?: number
  max?: number
  gt?: number
  lt?: number
  options?: string[]
}

export interface StrategyInfo {
  id: string
  name: string
  category: 'stock' | 'futures'
  category_label: string
  style: string
  summary: string
  aliases: string[]
  default_universe: string
  asset_types: string[]
  min_symbols: number
  params: ParamSpec[]
  derived?: boolean
  base_id?: string
  base_name?: string
}

export interface StrategyDetail extends StrategyInfo {
  doc: string
  source: string
  source_file: string
}

export interface MarketOverview {
  ranges: Record<string, [string, string]>
  stocks: { symbol: string; name: string; industry: string }[]
  futures: { symbol: string; name: string; exchange: string; sector: string; multiplier: number; margin_rate: number }[]
  industries: { symbol: string; name: string }[]
  benchmarks: { code: string; name: string }[]
  universe_presets: { value: string; label: string }[]
}

export interface BacktestConfig {
  start: string
  end: string
  initial_capital?: number
  stock_commission?: number
  stock_min_commission?: number
  stock_slippage?: number
  futures_slippage_ticks?: number
  futures_commission_scale?: number
  max_margin_ratio?: number
  risk_free_rate?: number
  benchmarks?: string[]
}

export interface Metrics {
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe: number
  calmar: number
  volatility: number
  win_rate: number
  profit_loss_ratio: number | null
  trade_count: number
  sortino: number
  profit_factor: number
  avg_holding_days: number
  max_drawdown_days: number
  max_drawdown_peak: string | null
  max_drawdown_trough: string | null
  avg_gross_exposure: number
  annual_turnover: number
  total_cost: number
  cost_ratio: number
  fill_count: number
  final_equity: number
  initial_capital: number
  [k: string]: any
}

export interface BenchmarkStats {
  code: string
  name: string
  total_return: number
  annual_return: number
  volatility: number
  sharpe: number
  max_drawdown: number
  calmar: number
  beta?: number
  alpha?: number
  information_ratio?: number
  tracking_error?: number
  correlation?: number
  excess_annual_return: number
}

export interface Trade {
  symbol: string
  name: string
  side: string
  entry_date: string
  exit_date: string | null
  entry_price: number
  exit_price: number | null
  max_qty: number
  pnl: number
  cost: number
  holding_days: number
  is_open: boolean
  return_pct: number
}

export interface Fill {
  date: string
  symbol: string
  name: string
  action: string
  qty: number
  price: number
  amount: number
  fee: number
  slippage: number
  contract: string | null
  note: string
}

export interface ChartData {
  symbol: string
  name: string
  dates: string[]
  ohlc: [number, number, number, number][]
  lines: Record<string, (number | null)[]>
  marks: { date: string; action: string; qty: number; price: number; raw_price: number }[]
}

export interface BacktestPayload {
  id: string
  kind: 'single' | 'portfolio'
  title: string
  strategy: { id: string; name: string; category: string; style: string; derived_name?: string }
  params: Record<string, any>
  universe: { symbol: string; name: string }[]
  config: BacktestConfig & Record<string, any>
  metrics: Metrics
  benchmarks: Record<string, BenchmarkStats>
  series: {
    dates: string[]
    nav: number[]
    drawdown: number[]
    exposure: number[]
    benchmarks: Record<string, { name: string; nav: (number | null)[]; drawdown: (number | null)[] }>
    components: Record<string, (number | null)[]>
  }
  yearly: { years: number[]; columns: Record<string, (number | null)[]> }
  monthly: { month: string; ret: number | null }[]
  trades: Trade[]
  fills: Fill[]
  fills_truncated: boolean
  fill_total: number
  holdings_last: Holding[]
  charts: ChartData[]
  diagnostics: Record<string, any>
  warnings: string[]
  notes: string[]
  components: { label: string; strategy_id: string; name: string; weight: number; result_id: string; params: Record<string, any>; metrics: Record<string, number> }[]
  created_at: string
  elapsed: number
}

export interface BacktestRecord {
  id: string
  kind: string
  title: string
  strategy_id: string
  category: string
  start: string
  end: string
  summary: Record<string, number | null>
  params: Record<string, any>
  universe: string
  source: string
  created_at: string
}

export interface Provider {
  id: number
  name: string
  base_url: string
  api_key_masked: string
  has_key: boolean
  models: string[]
  enabled: boolean
  updated_at: string
}

export interface ModelRef { provider_id: number; model: string }
export interface Routing {
  primary: ModelRef | null
  fallbacks: ModelRef[]
  temperature: number
  timeout: number
  first_token_timeout: number
}

// 回测结果缓存（同一个结果在对话、历史、报告页之间复用）
const payloadCache = new Map<string, Promise<BacktestPayload>>()
export function getHoldings(id: string, date: string): Promise<Holding[]> {
  return api.get<Holding[]>(`/api/backtests/${id}/holdings?date=${date}`)
}

export const exportUrl = (id: string) => `/api/backtests/${id}/export`

export function getBacktest(id: string): Promise<BacktestPayload> {
  if (!payloadCache.has(id)) {
    const p = api.get<BacktestPayload>(`/api/backtests/${id}`)
    p.catch(() => payloadCache.delete(id))
    payloadCache.set(id, p)
  }
  return payloadCache.get(id)!
}
export function cacheBacktest(p: BacktestPayload) {
  payloadCache.set(p.id, Promise.resolve(p))
}
