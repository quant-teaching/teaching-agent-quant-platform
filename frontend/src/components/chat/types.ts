export interface ToolBlock {
  kind: 'tool'
  id: string
  name: string
  label: string
  status: 'running' | 'ok' | 'error'
  error?: string | null
  card?: any
}
export interface TextBlock {
  kind: 'text'
  text: string
}
export type Block = ToolBlock | TextBlock

export interface UiMessage {
  key: string
  role: 'user' | 'assistant'
  text?: string // 用户消息
  blocks: Block[]
  streaming?: boolean
  model?: string | null
  switches: { from: string; to: string; reason: string }[]
  factCheck?: { status: string; checked: number; unmatched: string[] } | null
  disclaimer?: boolean
  error?: string | null
}

export const DISCLAIMER = '⚠️ 本结果为教学回测模拟，历史回测不代表未来表现，不构成任何投资建议。'
