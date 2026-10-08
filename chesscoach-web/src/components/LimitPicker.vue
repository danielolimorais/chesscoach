<template>
  <div class="limit" role="group" aria-label="Quantidade de partidas">
    <span class="label">Partidas</span>
    <button
      v-for="n in options"
      :key="n"
      type="button"
      :class="{ on: modelValue === n }"
      :aria-pressed="modelValue === n"
      @click="emit('update:modelValue', n)"
    >
      {{ n }}
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
const options = [20, 30, 50]
</script>

<style scoped>
.limit {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.label { padding: 0 0.6rem 0 0.5rem; font-size: 0.8rem; color: var(--muted); }
button {
  min-width: 2.6rem;
  padding: 0.3rem 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-radius: 7px;
  cursor: pointer;
}
button:hover { color: var(--strong); }
button.on { color: var(--strong); background: var(--surface); box-shadow: var(--shadow-sm); }
</style>
