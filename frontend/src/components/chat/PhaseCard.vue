<script setup lang="ts">
// 自主研究的过程卡片：研究计划 → 第 n 轮执行 → 反思评估 → …… → 研究报告；以及"先计划后执行"中已确认的计划。
import { CircleCheck, CircleDashed, Compass, FileText, FlaskConical, ListChecks, Target } from 'lucide-vue-next'
import type { PhaseBlock, PlanBlock } from './types'

defineProps<{ block: PhaseBlock | PlanBlock }>()
const argText = (a: Record<string, any>) => Object.entries(a ?? {}).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join('，')
</script>

<template>
  <!-- 已确认的计划 -->
  <div v-if="block.kind === 'plan'" class="card plan">
    <div class="title"><ListChecks :size="15" /> 执行的计划</div>
    <p v-if="block.intro" class="intro">{{ block.intro }}</p>
    <ol>
      <li v-for="(s, i) in block.steps" :key="i"><b>{{ s.tool_label || s.tool }}</b> <code>{{ argText(s.args) }}</code><span v-if="s.why"> — {{ s.why }}</span></li>
    </ol>
  </div>

  <!-- 研究计划 -->
  <div v-else-if="block.name === 'research_plan'" class="card research">
    <div class="title"><Compass :size="15" /> 研究计划 <span class="badge">智能体自主制定</span></div>
    <div class="kv"><Target :size="13" /><span><b>目标</b>{{ block.goal }}</span></div>
    <div class="kv"><CircleCheck :size="13" /><span><b>达成标准</b>{{ block.criteria }}</span></div>
    <ol v-if="block.steps?.length">
      <li v-for="(s, i) in block.steps" :key="i">{{ s }}</li>
    </ol>
  </div>

  <!-- 第 n 轮开始 -->
  <div v-else-if="block.name === 'iteration'" class="divider"><FlaskConical :size="13" /> {{ block.label }}</div>

  <!-- 反思 -->
  <div v-else-if="block.name === 'reflect'" class="card reflect" :class="{ met: block.goal_met }">
    <div class="title">
      <CircleCheck v-if="block.goal_met" :size="15" /><CircleDashed v-else :size="15" />
      {{ block.label }}
      <span class="badge" :class="{ ok: block.goal_met }">{{ block.goal_met ? '目标已达成' : '尚未达成' }}</span>
    </div>
    <p v-if="block.assessment" class="txt">{{ block.assessment }}</p>
    <p v-if="block.next && !block.stop_reason" class="next"><b>下一步：</b>{{ block.next }}</p>
    <p v-if="block.stop_reason" class="stop">研究结束：{{ block.stop_reason }}</p>
  </div>

  <div v-else-if="block.name === 'report'" class="divider report"><FileText :size="13" /> {{ block.label }}</div>
</template>

<style scoped>
.card { margin: 8px 0; padding: 10px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); font-size: 13px; animation: pop 0.35s var(--ease-out) both; }
.title { display: flex; align-items: center; gap: 6px; font-weight: 650; margin-bottom: 6px; }
.research { --tone: var(--t-teal); border-color: color-mix(in srgb, var(--tone) 40%, var(--border)); background: linear-gradient(135deg, var(--t-teal-soft), var(--surface) 60%); }
.research .title svg { color: var(--tone); }
.plan .title svg { color: var(--t-violet); }
.badge { margin-left: auto; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; color: var(--warn); background: var(--warn-soft); }
.research .badge { color: var(--t-teal); background: var(--surface); }
.badge.ok { color: var(--t-green); background: var(--t-green-soft); }
.kv { display: flex; gap: 6px; margin: 3px 0; line-height: 1.6; }
.kv svg { flex-shrink: 0; margin-top: 4px; color: var(--text-3); }
.kv b { margin-right: 6px; }
ol { margin: 6px 0 0; padding-left: 20px; line-height: 1.7; color: var(--text-2); }
code { font-family: var(--mono); font-size: 11.5px; color: var(--text-3); }
.intro { margin: 0 0 4px; color: var(--text-2); }
.divider { display: flex; align-items: center; gap: 6px; margin: 14px 0 6px; font-size: 12.5px; font-weight: 650; color: var(--t-teal); }
.divider::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, color-mix(in srgb, var(--t-teal) 40%, transparent), transparent); }
.divider.report { color: var(--primary-ink); }
.reflect { border-left: 3px solid var(--warn); }
.reflect.met { border-left-color: var(--t-green); }
.reflect .title svg { color: var(--warn); }
.reflect.met .title svg { color: var(--t-green); }
.txt, .next, .stop { margin: 4px 0 0; line-height: 1.65; color: var(--text-2); }
.stop { font-size: 12px; color: var(--text-3); }
</style>
