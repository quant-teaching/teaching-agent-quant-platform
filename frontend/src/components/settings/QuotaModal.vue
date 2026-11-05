<script setup lang="ts">
// 设置每日平台模型对话次数：沿用默认（班级 / 角色默认值）、自定义次数，或（仅角色默认时）不限
import { NButton, NInputNumber, NModal, NRadio, NRadioGroup } from 'naive-ui'
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{ title: string; value: number | null; inheritLabel?: string; allowUnlimited?: boolean; hint?: string }>(),
  { inheritLabel: '沿用默认值', allowUnlimited: false, hint: '' })
const show = defineModel<boolean>('show', { default: false })
const emit = defineEmits<{ save: [value: number | null] }>()
const mode = ref<'inherit' | 'custom'>('inherit')
const num = ref<number | null>(30)
watch(show, (v) => {
  if (!v) return
  mode.value = props.value === null ? 'inherit' : 'custom'
  num.value = props.value ?? 30
})
function save() {
  emit('save', mode.value === 'inherit' ? null : (num.value ?? 0))
  show.value = false
}
</script>

<template>
  <NModal v-model:show="show" preset="card" :title="title" :bordered="false" style="width: 420px; max-width: calc(100vw - 32px)">
    <NRadioGroup v-model:value="mode" class="qm">
      <NRadio value="inherit">{{ allowUnlimited ? '不限次数' : inheritLabel }}</NRadio>
      <NRadio value="custom">自定义每日次数</NRadio>
    </NRadioGroup>
    <NInputNumber v-if="mode === 'custom'" v-model:value="num" :min="0" :max="100000" class="qm-num"><template #suffix>次 / 天</template></NInputNumber>
    <p class="muted qm-hint">{{ hint || '每发送一条消息算一次（一轮对话中的多次工具调用不重复计算）；只统计平台渠道，用自己的模型渠道不占额度。每天 0 点重置。' }}</p>
    <NButton type="primary" block @click="save">保存</NButton>
  </NModal>
</template>

<style scoped>
.qm { display: flex; flex-direction: column; gap: 8px; }
.qm-num { margin-top: 12px; width: 100%; }
.qm-hint { margin: 12px 0 14px; font-size: 12.5px; line-height: 1.6; }
</style>
