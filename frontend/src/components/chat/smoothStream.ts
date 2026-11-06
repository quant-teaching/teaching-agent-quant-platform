// 让模型的流式输出以平稳的速度逐字出现。
//
// 模型返回的片段大小和间隔都不均匀（有时一次几十个字、有时停顿半秒），直接拼到页面上会一顿一顿的。
// 这里把收到的文字先放进缓冲区，再按"接近模型的平均输出速度、略慢一点"的节奏逐字放出：
// - 缓冲区始终留有少量余量，模型偶尔停顿时文字仍在匀速流动；
// - 积压过多时自动加速，界面落后模型不超过 MAX_LAG 秒；
// - 工具调用等非文字事件和文字排在同一个队列里，按原顺序生效，不会插到半句话中间。

import type { ChatEvent } from '@/api/chat'

const MIN_CPS = 24 // 最低速度（字/秒）
const MAX_LAG = 1.2 // 缓冲区最多积压约这么多秒的文字
const FOLLOW = 0.92 // 以模型平均速度的这个比例放出，缓冲区保持少量余量
const FRAME_MS = 33 // 约 30 帧/秒刷新正文，Markdown 重新渲染不会太频繁

type Item = { kind: 'text'; text: string } | { kind: 'event'; e: ChatEvent }

export interface SmoothStream {
  push(e: ChatEvent): void
  /** 丢弃队列中还没显示的文字（模型切换时，失败模型的输出不再显示） */
  dropText(): void
  /** 立即把队列全部生效（停止生成、页面在后台时） */
  flush(): void
  /** 队列全部显示完成 */
  drained(): Promise<void>
  dispose(): void
}

export function createSmoothStream(apply: (e: ChatEvent) => void): SmoothStream {
  const queue: Item[] = []
  let backlog = 0 // 队列中未显示的字数
  let received = 0 // 本轮收到的字数
  let firstAt = 0 // 本轮第一段文字到达的时间
  let budget = 0 // 累计可放出的字数（小数部分跨帧保留）
  let last = 0
  let timer: number | null = null
  let waiters: (() => void)[] = []
  const reduced = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

  const speed = (now: number) => {
    const elapsed = Math.max((now - firstAt) / 1000, 0.6)
    const avg = received / elapsed
    return Math.max(MIN_CPS, avg * FOLLOW, backlog / MAX_LAG)
  }

  function take(n: number): number {
    // 从队首文字中取出最多 n 个字，不拆开代理对（emoji 等）
    const head = queue[0] as { kind: 'text'; text: string }
    let cut = Math.min(n, head.text.length)
    const code = head.text.charCodeAt(cut - 1)
    if (cut < head.text.length && code >= 0xd800 && code <= 0xdbff) cut += 1
    apply({ type: 'delta', text: head.text.slice(0, cut) } as ChatEvent)
    head.text = head.text.slice(cut)
    backlog -= cut
    if (!head.text) queue.shift()
    return cut
  }

  function drain(all: boolean) {
    while (queue.length) {
      const head = queue[0]
      if (head.kind === 'event') {
        queue.shift()
        apply(head.e)
        continue
      }
      if (all) { take(head.text.length); continue }
      if (budget < 1) break
      budget -= take(Math.floor(budget))
    }
    if (!queue.length) {
      budget = 0
      const w = waiters
      waiters = []
      w.forEach((f) => f())
    }
  }

  function tick() {
    timer = null
    const now = performance.now()
    const dt = Math.min((now - last) / 1000, 0.25)
    last = now
    budget += speed(now) * dt
    drain(false)
    if (queue.length) schedule()
  }

  function schedule() {
    if (timer == null) timer = window.setTimeout(tick, FRAME_MS)
  }

  const onVisibility = () => { if (document.hidden) drain(true) }
  document.addEventListener('visibilitychange', onVisibility)

  return {
    push(e) {
      if (e.type === 'model') { received = 0; firstAt = 0 }
      if (e.type === 'delta') {
        if (!e.text) return
        const now = performance.now()
        if (!firstAt) firstAt = now
        received += e.text.length
        backlog += e.text.length
        const tail = queue[queue.length - 1]
        if (tail && tail.kind === 'text') tail.text += e.text
        else queue.push({ kind: 'text', text: e.text })
      } else {
        queue.push({ kind: 'event', e })
      }
      if (reduced || document.hidden) return drain(true)
      if (timer == null) { last = performance.now(); schedule() }
    },
    dropText() {
      for (let i = queue.length - 1; i >= 0; i--) if (queue[i].kind === 'text') queue.splice(i, 1)
      backlog = 0
    },
    flush() { drain(true) },
    drained() {
      if (!queue.length) return Promise.resolve()
      return new Promise((r) => waiters.push(r))
    },
    dispose() {
      if (timer != null) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      drain(true)
    },
  }
}
