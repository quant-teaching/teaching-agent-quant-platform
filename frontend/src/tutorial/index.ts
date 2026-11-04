// 新手教程目录。正文是同目录下的 Markdown 文件，打包时内联进前端，不需要后端接口。
const files = import.meta.glob('./*.md', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

export type Tone = 'blue' | 'violet' | 'teal' | 'amber' | 'rose'

export interface Chapter {
  id: string
  title: string
  summary: string
  minutes: number
  body: string
  category: Category
  index: number // 全书中的序号，从 1 开始
}

export interface Category {
  key: string
  title: string
  desc: string
  tone: Tone
  chapters: Chapter[]
}

const RAW: { key: string; title: string; desc: string; tone: Tone; items: [string, string, string, number][] }[] = [
  {
    key: 'start', title: '准备出发', desc: '认识平台，学会登录和找到各个功能', tone: 'blue',
    items: [
      ['01-welcome', '欢迎来到量化策略教学平台', '平台能做什么、这套教程怎么读', 4],
      ['02-tour', '注册登录与界面导览', '账号、侧边栏和深色模式', 4],
    ],
  },
  {
    key: 'basics', title: '量化零基础', desc: 'K 线、均线、回测和指标，量化的基本功', tone: 'violet',
    items: [
      ['03-what-is-quant', '什么是量化交易', '规则化、可检验、有纪律的交易方法', 6],
      ['04-kline-indicators', 'K 线、均线与常用指标', '看懂价格数据和技术指标', 8],
      ['05-backtest', '回测：用历史检验想法', '引擎如何逐日模拟交易', 7],
      ['06-metrics', '看懂回测报告里的指标', '收益、回撤、夏普、胜率一次讲清', 8],
    ],
  },
  {
    key: 'practice', title: '动手实操', desc: '每一章都带你在网站上真正做一遍', tone: 'teal',
    items: [
      ['07-first-chat', '第一次对话：让智能助手帮你回测', '用一句话完成调策略、回测和解读', 7],
      ['08-library', '逛算法库：读懂一个策略', '教学说明、参数、源码与衍生策略', 6],
      ['09-lab', '回测实验室：自己调参数', '控制变量，一次只改一个参数', 7],
      ['10-portfolio', '组合实验室：把策略组合起来', '用相关性和再平衡分散风险', 6],
      ['11-history', '回测记录、报告与数据导出', '排序对比、查看持仓、下载 CSV', 5],
    ],
  },
  {
    key: 'advanced', title: '进阶与避坑', desc: '参数优化、期货和回测陷阱', tone: 'amber',
    items: [
      ['12-optimize', '参数优化与过拟合', '敏感性分析和样本外验证', 8],
      ['13-futures', '期货与 CTA 入门', '做空、保证金、合约乘数与换月', 8],
      ['14-pitfalls', '回测常见陷阱与学习路线', '五个陷阱和四周学习计划', 6],
      ['15-faq', '常见问题', '遇到问题先来这里找答案', 4],
    ],
  },
]

let n = 0
export const CATEGORIES: Category[] = RAW.map((c) => {
  const cat: Category = { key: c.key, title: c.title, desc: c.desc, tone: c.tone, chapters: [] }
  cat.chapters = c.items.map(([id, title, summary, minutes]) => ({
    id, title, summary, minutes, category: cat, index: ++n,
    // 正文第一行的一级标题由页面自己渲染，这里去掉避免重复
    body: (files[`./${id}.md`] ?? '').replace(/^#\s+[^\n]*\n+/, ''),
  }))
  return cat
})

export const CHAPTERS: Chapter[] = CATEGORIES.flatMap((c) => c.chapters)
export const TOTAL_MINUTES = CHAPTERS.reduce((s, c) => s + c.minutes, 0)
