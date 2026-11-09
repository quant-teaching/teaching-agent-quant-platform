// 把服务器保存的消息（含工具卡片、确认、研究阶段等事件）转换成对话页的展示结构
import { DISCLAIMER, type Block, type UiMessage } from './types'

export function fromServer(m: any, pendingId: number | null = null): UiMessage {
  if (m.role === 'user') return { key: `u${m.id}`, role: 'user', text: m.content, blocks: [], switches: [] }
  const blocks: Block[] = []
  const switches: UiMessage['switches'] = []
  let factCheck = null
  for (const e of m.events as any[]) {
    if (e.kind === 'tool') blocks.push({ kind: 'tool', id: e.id, name: e.name, label: e.label, status: e.ok ? 'ok' : 'error', error: e.error, card: e.card })
    else if (e.kind === 'phase' || e.kind === 'plan') blocks.push(e)
    else if (e.kind === 'approval') {
      // 只有服务器上仍在等待的那一步可以继续确认，其余的视为失效
      const status = e.status === 'pending' && pendingId !== m.id ? 'expired' : e.status
      blocks.push({ ...e, status })
    } else if (e.kind === 'fact_check') factCheck = e
    else if (e.kind === 'model_switch') switches.push({ from: e.from, to: e.to, reason: e.reason })
  }
  let text: string = m.content
  const disclaimer = text.trimEnd().endsWith(DISCLAIMER)
  if (disclaimer) text = text.trimEnd().slice(0, -DISCLAIMER.length)
  blocks.push({ kind: 'text', text })
  return { key: `a${m.id}`, role: 'assistant', blocks, switches, factCheck, disclaimer, model: m.model }
}
