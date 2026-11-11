// 流式对话：POST /api/chat、/api/chat/resume，GET 重新订阅进行中的回答，读取 SSE 事件流
import { handleUnauthorized } from './client'

/** 指定对话使用的模型；null 表示自动（按模型设置里的主备顺序） */
export interface ModelRef { provider_id: number; model: string }

export interface ChatEvent {
  type: string
  [k: string]: any
}

/** 学生对智能体的控制设置（见「智能体控制」面板） */
export type AgentMode = 'auto' | 'confirm' | 'plan' | 'research'
export interface AgentControl {
  mode: AgentMode
  tools: string[]
  strategies: string[] | null
  max_backtests: number
  max_iterations: number
}

async function readSse(url: string, body: unknown, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  const resp = await fetch(url, body === undefined
    ? { headers: { Accept: 'text/event-stream' }, signal }
    : { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify(body), signal })
  if (resp.status === 401) handleUnauthorized(url)
  if (!resp.ok || !resp.body) {
    let detail = `请求失败（${resp.status}）`
    try {
      const j = await resp.json()
      if (typeof j.detail === 'string') detail = j.detail
    } catch { /* 非 JSON */ }
    throw new Error(detail)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split(/\r?\n\r?\n/)
    buf = parts.pop() ?? ''
    for (const part of parts) {
      const data = part
        .split(/\r?\n/)
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart())
        .join('\n')
      if (!data) continue
      try {
        onEvent(JSON.parse(data))
      } catch { /* 心跳等非 JSON 行 */ }
    }
  }
}

export function streamChat(
  message: string,
  sessionId: string | null,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
  model: ModelRef | null = null,
  control: AgentControl | null = null,
): Promise<void> {
  return readSse('/api/chat', { message, session_id: sessionId, model, control }, onEvent, signal)
}

/** 学生确认工具调用或计划后，让智能体从暂停处继续 */
export function resumeChat(
  sessionId: string,
  decision: Record<string, any>,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
  model: ModelRef | null = null,
): Promise<void> {
  return readSse('/api/chat/resume', { session_id: sessionId, decision, model }, onEvent, signal)
}

/** 重新订阅正在生成的回答（离开页面后回来）：服务端从头回放事件并继续推送 */
export function followChat(sessionId: string, onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  return readSse(`/api/chat/sessions/${sessionId}/live`, undefined, onEvent, signal)
}
