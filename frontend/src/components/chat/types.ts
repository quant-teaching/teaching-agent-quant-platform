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
/** 自主研究的阶段：研究计划、第 n 轮、反思、报告 */
export interface PhaseBlock {
  kind: 'phase'
  name: string
  label: string
  goal?: string
  criteria?: string
  steps?: string[]
  iteration?: number
  goal_met?: boolean
  assessment?: string
  next?: string
  stop_reason?: string
}
export interface PlanStep { tool: string; args: Record<string, any>; why?: string; label?: string; tool_label?: string }
/** 已确认执行的计划 */
export interface PlanBlock { kind: 'plan'; intro?: string; steps: PlanStep[] }
/** 智能体暂停，等学生确认工具调用（tools）或审核计划（plan） */
export interface ApprovalBlock {
  kind: 'approval'
  type: 'tools' | 'plan'
  status: 'pending' | 'submitting' | 'done' | 'cancelled' | 'expired'
  text?: string
  intro?: string
  calls?: { id: string; name: string; args: Record<string, any>; label: string; tool?: string }[]
  steps?: PlanStep[]
  items?: { label: string; action: 'approved' | 'edited' | 'rejected' }[]
  feedback?: string
  edited?: boolean
}
export type Block = ToolBlock | TextBlock | PhaseBlock | PlanBlock | ApprovalBlock

export interface UiMessage {
  key: string
  role: 'user' | 'assistant'
  text?: string // 用户消息
  blocks: Block[]
  streaming?: boolean
  status?: string // 正在制定计划、正在反思等临时状态
  model?: string | null
  switches: { from: string; to: string; reason: string }[]
  factCheck?: { status: string; checked: number; unmatched: string[] } | null
  disclaimer?: boolean
  error?: string | null
}

export const DISCLAIMER = '⚠️ 本结果为教学回测模拟，历史回测不代表未来表现，不构成任何投资建议。'
