<template>
  <!-- Barra de vitórias / empates / derrotas. A legenda e os números ficam ao lado, no componente pai. -->
  <span class="wdl" role="img" :aria-label="`${stats.wins} vitórias, ${stats.draws} empates, ${stats.losses} derrotas`">
    <span
      v-for="seg in segments"
      :key="seg.key"
      :class="['seg', seg.key]"
      :style="{ flexGrow: seg.value }"
      :title="`${seg.label}: ${seg.value}`"
    ></span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ stats: { wins: number; draws: number; losses: number } }>()

const segments = computed(() =>
  [
    { key: 'win', label: 'Vitórias', value: props.stats.wins },
    { key: 'draw', label: 'Empates', value: props.stats.draws },
    { key: 'loss', label: 'Derrotas', value: props.stats.losses },
  ].filter((s) => s.value > 0),
)
</script>

<style scoped>
.wdl { display: flex; gap: 2px; height: 10px; min-width: 60px; }
.seg { min-width: 4px; border-radius: 4px; }
.seg.win { background: var(--win); }
.seg.draw { background: var(--draw); }
.seg.loss { background: var(--loss); }
</style>
