// 流式对话：POST /api/chat，读取 SSE 事件流
import { handleUnauthorized } from './client'

/** 指定对话使用的模型；null 表示自动（按模型设置里的主备顺序） */
export interface ModelRef { provider_id: number; model: string }

export interface ChatEvent {
  type: string
  [k: string]: any
}

export async function streamChat(
  message: string,
  sessionId: string | null,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
  model: ModelRef | null = null,
): Promise<void> {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, session_id: sessionId, model }),
    signal,
  })
  if (resp.status === 401) handleUnauthorized('/api/chat')
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
