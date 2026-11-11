<script setup lang="ts">
// 把文本中的搜索关键词高亮显示
import { computed } from 'vue'
import { splitHits } from '@/utils/search'

const props = defineProps<{ text: string; q?: string }>()
const parts = computed(() => splitHits(props.text, props.q ?? ''))
</script>

<template>
  <span><template v-for="(p, i) in parts" :key="i"><mark v-if="p.hit" class="hl">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template></span>
</template>
