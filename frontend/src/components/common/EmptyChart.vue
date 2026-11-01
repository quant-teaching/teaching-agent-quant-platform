<script setup lang="ts">
// 空状态插画：K 线逐根升起，净值线描出来，纯装饰
const candles = [
  [14, 62, 44, 70, 38], [30, 52, 40, 58, 34], [46, 48, 58, 66, 42], [62, 40, 30, 46, 24],
  [78, 34, 44, 52, 28], [94, 28, 20, 36, 14], [110, 22, 32, 40, 16], [126, 16, 10, 24, 6],
] // x, open, close, low, high（SVG 坐标，越小越高）
</script>

<template>
  <svg class="empty-chart" viewBox="0 0 140 84" aria-hidden="true">
    <line v-for="y in [20, 40, 60]" :key="y" x1="0" x2="140" :y1="y" :y2="y" class="grid" />
    <g v-for="(c, i) in candles" :key="i" class="candle" :class="c[2] < c[1] ? 'up' : 'dn'" :style="{ animationDelay: `${i * 0.08}s` }">
      <line :x1="c[0]" :x2="c[0]" :y1="c[4]" :y2="c[3]" />
      <rect :x="c[0] - 4" :y="Math.min(c[1], c[2])" width="8" :height="Math.max(2, Math.abs(c[1] - c[2]))" rx="1.5" />
    </g>
    <path class="nav" d="M4 66 C 24 58, 34 56, 46 54 S 70 44, 82 40 S 104 26, 118 20 S 132 12, 138 10" />
    <circle class="tip" cx="138" cy="10" r="3" />
  </svg>
</template>

<style scoped>
.empty-chart { width: 180px; height: 108px; overflow: visible; }
.grid { stroke: var(--border); stroke-dasharray: 3 4; }
.candle { transform-box: fill-box; transform-origin: bottom; animation: candle-in 0.5s var(--ease-spring) both; }
.candle line { stroke-width: 1.4; }
.up line { stroke: var(--up); } .up rect { fill: var(--up); opacity: 0.85; }
.dn line { stroke: var(--down); } .dn rect { fill: var(--down); opacity: 0.85; }
.nav { fill: none; stroke: var(--t-blue); stroke-width: 2.4; stroke-linecap: round; stroke-dasharray: 200; stroke-dashoffset: 200; animation: draw-line 1.4s var(--ease-out) 0.6s forwards; }
.tip { fill: var(--t-blue); opacity: 0; animation: pop 0.4s var(--ease-spring) 1.8s forwards, pulse-dot 2s ease-in-out 2.2s infinite; transform-box: fill-box; transform-origin: center; }
@keyframes candle-in { from { opacity: 0; transform: scaleY(0.2); } to { opacity: 1; transform: none; } }
@keyframes pulse-dot { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.6); } }
</style>
