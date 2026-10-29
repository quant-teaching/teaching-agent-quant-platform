// 图表配色。分类色按固定顺序分配（不循环），浅色/深色各自取对应色阶，均已通过色盲安全校验。
import { computed } from 'vue'
import { useTheme } from '@/stores/theme'

const LIGHT = {
  surface: '#ffffff',
  text1: '#1c1f24',
  text2: '#4b5260',
  text3: '#8a909c',
  grid: '#eceef1',
  axis: '#d4d7dd',
  series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  up: '#e34948',
  down: '#1baf7a',
  neutral: '#f0efec',
  tooltipBg: 'rgba(255,255,255,0.97)',
  tooltipBorder: '#e5e7eb',
  seq: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'],
}

const DARK = {
  surface: '#1a1a19',
  text1: '#f0efec',
  text2: '#c3c2b7',
  text3: '#8d8c84',
  grid: '#2a2b2a',
  axis: '#3a3b39',
  series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
  up: '#e66767',
  down: '#199e70',
  neutral: '#383835',
  tooltipBg: 'rgba(32,33,32,0.97)',
  tooltipBorder: '#3a3b39',
  seq: ['#184f95', '#1c5cab', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4'],
}

export type ChartTokens = typeof LIGHT

export function useChartTokens() {
  const theme = useTheme()
  return computed<ChartTokens>(() => (theme.isDark ? DARK : LIGHT))
}

/** 所有图表共用的坐标轴、网格、提示框样式 */
export function baseOption(t: ChartTokens) {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'inherit', color: t.text2 },
    animationDuration: 400,
    tooltip: {
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: t.text1, fontSize: 12 },
      extraCssText: 'border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.12);',
    },
  }
}

export function axisStyle(t: ChartTokens) {
  return {
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.text3, fontSize: 11 },
    splitLine: { lineStyle: { color: t.grid, width: 1, type: 'solid' as const } },
  }
}

export function hexAlpha(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

/** 涨跌发散色：红（涨）— 中性灰 — 绿（跌） */
export function divergingColor(t: ChartTokens, v: number, max: number): string {
  const x = Math.max(-1, Math.min(1, v / (max || 1)))
  const target = x >= 0 ? t.up : t.down
  return mix(t.neutral, target, Math.abs(x) * 0.9 + (x === 0 ? 0 : 0.1))
}

function mix(a: string, b: string, k: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * k))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}
