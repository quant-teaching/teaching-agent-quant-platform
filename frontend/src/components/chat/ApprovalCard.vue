<script setup lang="ts">
// 智能体暂停等待学生决定：
// - 每步确认：逐个批准 / 拒绝工具调用，可以修改参数，也可以写一句意见给智能体；
// - 先计划后执行：调整计划步骤的顺序、参数，删除或添加步骤，确认后按计划执行。
import { ArrowDown, ArrowUp, Ban, Check, CircleCheck, CircleX, Hand, ListChecks, Pencil, Play, Plus, Trash2, Undo2 } from 'lucide-vue-next'
import { NButton, NInput, NSelect } from 'naive-ui'
import { computed, ref } from 'vue'
import { useAgentControl } from '@/stores/agentControl'
import ArgsEditor from './ArgsEditor.vue'
import type { ApprovalBlock } from './types'

const props = defineProps<{ block: ApprovalBlock; busy?: boolean }>()
const emit = defineEmits<{ decide: [decision: Record<string, any>] }>()
const store = useAgentControl()

const live = computed(() => props.block.status === 'pending')
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x ?? null))

// -- 工具确认
const calls = ref((props.block.calls ?? []).map((c) => ({ ...c, args: clone(c.args ?? {}), action: 'approve' as 'approve' | 'reject', edit: false })))
const feedback = ref('')
const changed = (c: (typeof calls.value)[number]) => JSON.stringify(c.args) !== JSON.stringify(props.block.calls?.find((x) => x.id === c.id)?.args ?? {})
function submitTools() {
  emit('decide', {
    calls: Object.fromEntries(calls.value.map((c) => [c.id, { action: c.action, args: c.args }])),
    feedback: feedback.value.trim(),
  })
}

// -- 计划审核
const steps = ref((props.block.steps ?? []).map((s) => ({ ...s, args: clone(s.args ?? {}), edit: false })))
const adding = ref<string | null>(null)
const toolOptions = computed(() => (store.meta?.tools ?? []).filter((t) => store.control.tools.includes(t.name)).map((t) => ({ label: t.label, value: t.name })))
const label = (name: string) => store.toolMeta(name)?.label ?? name
function move(i: number, d: number) {
  const arr = steps.value
  const j = i + d
  if (j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
function addStep(name: string | null) {
  if (!name) return
  steps.value.push({ tool: name, tool_label: label(name), label: label(name), args: {}, why: '我自己添加的步骤', edit: true })
  adding.value = null
}
function submitPlan() {
  emit('decide', { action: 'approve', steps: steps.value.map(({ tool, args, why }) => ({ tool, args, why })) })
}

const argText = (a: Record<string, any>) => Object.entries(a ?? {}).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join('，')
const STATUS: Record<string, string> = { done: '已确认', cancelled: '已取消', expired: '已失效（没有确认就发送了新消息）', submitting: '已提交' }
const ACTION: Record<string, string> = { approved: '已批准', edited: '已修改参数', rejected: '已拒绝' }
</script>

<template>
  <!-- 等待确认 -->
  <div v-if="live || block.status === 'submitting'" class="card live" :class="block.type">
    <div class="head">
      <span class="ic"><Hand v-if="block.type === 'tools'" :size="15" /><ListChecks v-else :size="15" /></span>
      <div>
        <b>{{ block.type === 'tools' ? '智能体想执行下面的操作，需要你确认' : '智能体拟定了一份计划，请审核后再执行' }}</b>
        <p v-if="block.type === 'tools'">可以逐个批准或拒绝，也可以修改参数；拒绝时写下理由，智能体会据此调整。</p>
        <p v-else>{{ block.intro || '你可以调整步骤顺序、修改参数、删除或添加步骤。' }}</p>
      </div>
    </div>

    <template v-if="block.type === 'tools'">
      <div v-for="c in calls" :key="c.id" class="item" :class="{ rejected: c.action === 'reject' }">
        <div class="row">
          <span class="tl">{{ c.tool || label(c.name) }}</span>
          <span class="args-sum">{{ argText(c.args) || '无参数' }}</span>
          <span v-if="changed(c)" class="tag edited">已修改</span>
        </div>
        <div class="ops">
          <button :class="{ on: c.action === 'approve' }" :disabled="!live" @click="c.action = 'approve'"><Check :size="13" />批准</button>
          <button :class="{ on: c.action === 'reject', neg: true }" :disabled="!live" @click="c.action = 'reject'"><Ban :size="13" />拒绝</button>
          <button :disabled="!live || c.action === 'reject'" @click="c.edit = !c.edit"><Pencil :size="13" />{{ c.edit ? '收起参数' : '修改参数' }}</button>
          <button v-if="changed(c)" :disabled="!live" @click="c.args = clone(block.calls!.find((x) => x.id === c.id)!.args)"><Undo2 :size="13" />还原</button>
        </div>
        <ArgsEditor v-if="c.edit && c.action !== 'reject'" v-model="c.args" :tool="c.name" />
      </div>
      <NInput v-model:value="feedback" :disabled="!live" type="textarea" size="small" :autosize="{ minRows: 1, maxRows: 3 }"
        placeholder="（可选）给智能体的意见，例如：先不要改参数，用默认参数回测" class="fb" />
      <div class="foot">
        <NButton size="small" :disabled="!live || busy" @click="emit('decide', { action: 'reject_all', feedback: feedback.trim() })">
          <template #icon><Ban :size="14" /></template>全部拒绝
        </NButton>
        <NButton size="small" type="primary" :loading="block.status === 'submitting'" :disabled="!live || busy" @click="submitTools">
          <template #icon><Play :size="14" /></template>确认并继续
        </NButton>
      </div>
    </template>

    <template v-else>
      <ol class="steps">
        <li v-for="(s, i) in steps" :key="i" class="item">
          <div class="row">
            <span class="no">{{ i + 1 }}</span>
            <span class="tl">{{ s.tool_label || label(s.tool) }}</span>
            <span class="args-sum">{{ argText(s.args) || '无参数' }}</span>
          </div>
          <div v-if="s.why" class="why">{{ s.why }}</div>
          <div class="ops">
            <button :disabled="!live || i === 0" title="上移" @click="move(i, -1)"><ArrowUp :size="13" /></button>
            <button :disabled="!live || i === steps.length - 1" title="下移" @click="move(i, 1)"><ArrowDown :size="13" /></button>
            <button :disabled="!live" @click="s.edit = !s.edit"><Pencil :size="13" />{{ s.edit ? '收起参数' : '修改参数' }}</button>
            <button class="neg" :disabled="!live" @click="steps.splice(i, 1)"><Trash2 :size="13" />删除</button>
          </div>
          <ArgsEditor v-if="s.edit" v-model="s.args" :tool="s.tool" />
        </li>
      </ol>
      <div class="add">
        <NSelect v-model:value="adding" size="small" :options="toolOptions" placeholder="添加一步：选择工具" :disabled="!live"
          style="max-width: 240px" @update:value="addStep" />
        <Plus :size="14" class="muted" />
      </div>
      <div class="foot">
        <NButton size="small" :disabled="!live || busy" @click="emit('decide', { action: 'cancel' })">
          <template #icon><Ban :size="14" /></template>取消计划
        </NButton>
        <NButton size="small" type="primary" :loading="block.status === 'submitting'" :disabled="!live || busy || !steps.length" @click="submitPlan">
          <template #icon><Play :size="14" /></template>按计划执行（{{ steps.length }} 步）
        </NButton>
      </div>
    </template>
  </div>

  <!-- 已处理 -->
  <div v-else class="card done" :class="block.status">
    <div class="sum-head">
      <CircleCheck v-if="block.status === 'done'" :size="14" />
      <CircleX v-else :size="14" />
      <span>{{ block.type === 'tools' ? '工具调用' : '计划' }}{{ STATUS[block.status] ?? '' }}<template v-if="block.edited">（你修改了计划）</template></span>
    </div>
    <div v-if="block.items?.length && block.type === 'tools'" class="chips">
      <span v-for="(it, i) in block.items" :key="i" class="chip" :class="it.action">{{ ACTION[it.action] }} · {{ it.label }}</span>
    </div>
    <div v-if="block.feedback" class="quote">你的意见：{{ block.feedback }}</div>
  </div>
</template>

<style scoped>
.card { margin: 6px 0 10px; border-radius: 12px; animation: pop 0.35s var(--ease-out) both; }
.live { --tone: var(--t-amber); --tone-soft: var(--t-amber-soft); padding: 12px 14px; background: var(--surface); border: 1px solid color-mix(in srgb, var(--tone) 45%, var(--border)); box-shadow: 0 6px 20px color-mix(in srgb, var(--tone) 12%, transparent); }
.live.plan { --tone: var(--t-violet); --tone-soft: var(--t-violet-soft); }
.head { display: flex; gap: 10px; margin-bottom: 10px; }
.head .ic { width: 30px; height: 30px; flex-shrink: 0; border-radius: 9px; display: grid; place-items: center; color: #fff; background: var(--tone); }
.head b { font-size: 13.5px; }
.head p { margin: 2px 0 0; font-size: 12px; color: var(--text-2); line-height: 1.55; }
.steps { list-style: none; margin: 0; padding: 0; }
.item { padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface-2); margin-bottom: 6px; display: grid; gap: 6px; transition: opacity 0.2s, border-color 0.2s; }
.item.rejected { opacity: 0.55; border-style: dashed; }
.row { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.no { width: 20px; height: 20px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700; color: var(--tone); background: var(--tone-soft); align-self: center; }
.tl { font-weight: 650; font-size: 13px; white-space: nowrap; }
.args-sum { flex: 1; min-width: 0; font-family: var(--mono); font-size: 11.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag.edited { font-size: 11px; padding: 0 6px; border-radius: 999px; color: var(--primary-ink); background: var(--primary-soft); }
.why { font-size: 12px; color: var(--text-2); padding-left: 28px; }
.ops { display: flex; flex-wrap: wrap; gap: 4px; }
.ops button {
  display: inline-flex; align-items: center; gap: 3px; height: 24px; padding: 0 8px; border-radius: 7px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-2); font: inherit; font-size: 12px; cursor: pointer; transition: all 0.15s;
  white-space: nowrap; flex-shrink: 0;
}
.ops button:hover:not(:disabled) { border-color: var(--border-strong); color: var(--text-1); }
.ops button:disabled { opacity: 0.45; cursor: default; }
.ops button.on { color: #fff; background: var(--t-green); border-color: transparent; }
.ops button.on.neg { background: var(--up); }
.ops button.neg:not(.on):hover:not(:disabled) { color: var(--up); }
.fb { margin-top: 2px; }
.add { display: flex; align-items: center; gap: 6px; margin: 2px 0 4px; }
.foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }

.done { padding: 8px 12px; background: var(--surface-2); border: 1px solid var(--border); font-size: 12.5px; color: var(--text-2); }
.sum-head { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.done.done .sum-head svg { color: var(--t-green); }
.done.cancelled .sum-head svg, .done.expired .sum-head svg { color: var(--text-3); }
.chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.chip { font-size: 11.5px; padding: 1px 8px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); }
.chip.approved { color: var(--t-green); }
.chip.edited { color: var(--primary-ink); }
.chip.rejected { color: var(--up); text-decoration: line-through; }
.quote { margin-top: 6px; font-size: 12px; color: var(--text-2); border-left: 3px solid var(--border-strong); padding-left: 8px; }
.muted { color: var(--text-3); }
</style>
