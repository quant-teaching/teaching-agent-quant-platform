<script setup lang="ts">
// 页面顶部横幅：彩色渐变底 + 网格纹理 + 漂移光斑 + 右侧装饰走势线，左侧图标、标题、说明，下方可放统计数字
import type { Component } from 'vue'

withDefaults(defineProps<{ title: string; desc?: string; icon: Component; tone?: 'blue' | 'violet' | 'teal' | 'amber' | 'rose' }>(), { tone: 'blue' })
</script>

<template>
  <header class="hero" :class="`tone-${tone}`">
    <span class="blob b1" /><span class="blob b2" />
    <svg class="deco" viewBox="0 0 320 120" preserveAspectRatio="none" aria-hidden="true">
      <path class="deco-area" d="M0 100 L30 88 L60 92 L90 70 L120 76 L150 52 L180 60 L210 38 L240 46 L270 22 L300 30 L320 14 L320 120 L0 120 Z" />
      <path class="deco-line" d="M0 100 L30 88 L60 92 L90 70 L120 76 L150 52 L180 60 L210 38 L240 46 L270 22 L300 30 L320 14" />
    </svg>
    <div class="row">
      <div class="icon"><component :is="icon" :size="24" :stroke-width="1.9" /></div>
      <div class="text">
        <h1>{{ title }}</h1>
        <p v-if="desc">{{ desc }}</p>
      </div>
      <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
    </div>
    <div v-if="$slots.default" class="extra"><slot /></div>
  </header>
</template>

<style scoped>
.hero {
  position: relative; overflow: hidden; margin-bottom: 20px; padding: 22px 26px;
  border-radius: 18px; border: 1px solid color-mix(in srgb, var(--tone) 22%, var(--border));
  background:
    linear-gradient(color-mix(in srgb, var(--tone) 7%, transparent) 1px, transparent 1px) 0 0 / 28px 28px,
    linear-gradient(90deg, color-mix(in srgb, var(--tone) 7%, transparent) 1px, transparent 1px) 0 0 / 28px 28px,
    linear-gradient(120deg, var(--surface) 30%, var(--tone-soft));
  box-shadow: var(--shadow-sm);
}
.blob { position: absolute; border-radius: 50%; filter: blur(40px); pointer-events: none; animation: drift 14s ease-in-out infinite; }
.b1 { width: 240px; height: 240px; right: 6%; top: -120px; background: color-mix(in srgb, var(--tone) 28%, transparent); }
.b2 { width: 180px; height: 180px; right: 30%; bottom: -120px; background: color-mix(in srgb, var(--tone) 16%, transparent); animation-delay: -6s; }
.deco { position: absolute; right: 0; bottom: 0; width: min(42%, 420px); height: 100%; pointer-events: none; opacity: 0.9;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 40%); mask-image: linear-gradient(90deg, transparent, #000 40%); }
.deco-line { fill: none; stroke: var(--tone); stroke-width: 2; vector-effect: non-scaling-stroke; opacity: 0.55;
  stroke-dasharray: 600; stroke-dashoffset: 600; animation: draw-line 1.8s var(--ease-out) 0.2s forwards; }
.deco-area { fill: color-mix(in srgb, var(--tone) 10%, transparent); opacity: 0; animation: rise 1s ease 0.8s forwards; }
.row { position: relative; display: flex; align-items: center; gap: 16px; }
.icon {
  width: 52px; height: 52px; flex-shrink: 0; border-radius: 15px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(140deg, color-mix(in srgb, var(--tone) 75%, #fff), var(--tone));
  box-shadow: 0 8px 22px color-mix(in srgb, var(--tone) 38%, transparent), inset 0 1px 0 rgba(255, 255, 255, 0.35);
  animation: pop 0.6s var(--ease-spring) both;
}
.text { flex: 1; min-width: 0; }
h1 { margin: 0; font-size: 23px; font-weight: 700; letter-spacing: 0.3px; color: var(--text-1); }
p { margin: 4px 0 0; color: var(--text-2); font-size: 13.5px; max-width: 760px; }
.actions { display: flex; gap: 8px; flex-shrink: 0; }
.extra { position: relative; margin-top: 18px; }
@media (max-width: 640px) {
  .hero { padding: 18px; }
  .row { flex-wrap: wrap; }
  .icon { width: 44px; height: 44px; }
  h1 { font-size: 19px; }
  .deco { width: 70%; opacity: 0.5; }
}
</style>
