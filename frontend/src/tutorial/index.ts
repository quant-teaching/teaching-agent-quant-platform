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
    key: 'start', title: '准备出发', desc: '认识平台，注册登录，找到每一个功能', tone: 'blue',
    items: [
      ['01-welcome', '欢迎来到量化策略教学平台', '这套教程写给谁、学完能做到什么、怎么读', 5],
      ['02-account', '注册与登录', '邀请码、密码规则、自动登录与修改密码', 4],
      ['03-tour', '界面导览：每个按钮在哪里', '侧边栏、页面横幅、智能助手的三栏布局', 5],
    ],
  },
  {
    key: 'basics', title: '金融与量化入门', desc: '股票市场常识、量化是什么、指标与回测原理', tone: 'violet',
    items: [
      ['04-market-basics', '股票市场的基础知识', 'A 股规则、交易成本、指数、分红送股', 8],
      ['05-what-is-quant', '什么是量化交易', '规则化、可检验、有纪律，以及四类策略思路', 7],
      ['06-kline', 'K 线与价格数据', '开高低收、涨跌幅、复权与 K 线图', 7],
      ['07-indicators', '均线与常用技术指标', '均线、EMA、布林带、RSI、MACD、KDJ、ATR 手算', 12],
      ['08-backtest', '回测：用历史检验想法', '引擎每天做的三件事，用数字走一遍', 9],
      ['09-return-risk', '看懂收益与风险指标', '用一组净值手算收益、回撤、夏普、卡玛', 10],
      ['10-trade-metrics', '看懂交易指标和诊断分析', '胜率、盈亏比、利润因子与策略"体检报告"', 9],
    ],
  },
  {
    key: 'practice', title: '动手实操', desc: '每一章都带你在网站上真正操作一遍', tone: 'teal',
    items: [
      ['11-first-chat', '第一次对话：让智能助手帮你回测', '发出第一句话，看懂步骤、报告与优化建议', 8],
      ['12-talk-tips', '和助手高效对话的技巧', '句式速查、多轮追问、选择模型、出错处理', 8],
      ['13-library', '逛算法库：读懂一个策略', '教学说明的结构、参数页、源码与衍生策略', 7],
      ['14-lab', '回测实验室：自己调参数', '逐项讲解参数栏，完成一次调参练习', 9],
      ['15-report', '读一份完整的回测报告', '每个标签页讲什么，以及 8 问读报告清单', 9],
      ['16-portfolio', '组合实验室：把策略组合起来', '相关性、再平衡与分散化比率', 7],
      ['17-history', '回测记录与数据导出', '排序对比、分享报告、导出 CSV 并用 Excel 分析', 6],
    ],
  },
  {
    key: 'advanced', title: '进阶与避坑', desc: '参数优化、实验方法、期货、回测陷阱与速查', tone: 'amber',
    items: [
      ['18-optimize', '参数优化与过拟合', '敏感性分析、样本内外验证、选高原不选山峰', 9],
      ['19-experiment', '用实验方法研究一个策略', '五个步骤、控制变量、实验记录与写结论', 8],
      ['20-futures', '期货与 CTA 入门', '做空、保证金、合约乘数、换月与 10 个期货策略', 10],
      ['21-pitfalls', '回测常见陷阱', '未来函数、幸存者偏差、成本、过拟合、样本太少', 7],
      ['22-roadmap', '学习路线与实验报告', '四周学习计划、报告模板与推荐题目', 6],
      ['23-glossary', '名词速查表', '市场、期货、指标、回测四类名词一表查清', 5],
      ['24-faq', '常见问题', '账号、助手、回测中遇到问题先来这里找答案', 6],
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
