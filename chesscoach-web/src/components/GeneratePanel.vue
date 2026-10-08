<template>
  <div class="generate">
    <!-- antes de gerar -->
    <div v-if="stage === 'idle'" class="card box">
      <span class="icon" aria-hidden="true">♞</span>
      <h1>Gerar relatório de {{ nick }}</h1>
      <p class="muted">
        Baixamos as partidas mais recentes do Chess.com, analisamos cada lance com o Stockfish e
        resumimos seus resultados, aberturas e erros mais comuns.
      </p>
      <LimitPicker :model-value="limit" @update:model-value="emit('update:limit', $event)" />
      <button class="btn big" type="button" @click="emit('generate')">Gerar relatório</button>
      <p class="muted small">Na primeira vez leva de 1 a 3 minutos. Partidas já analisadas ficam salvas.</p>
    </div>

    <!-- gerando / erro -->
    <div v-else class="card box progress">
      <h1>{{ stage === 'error' ? 'Não foi possível gerar o relatório' : 'Gerando relatório' }}</h1>
      <p v-if="stage !== 'error'" class="muted">Pode deixar esta aba aberta; o relatório aparece quando terminar.</p>

      <ol class="steps">
        <li v-for="step in steps" :key="step.key" :class="['step', step.state]">
          <span class="marker" aria-hidden="true">
            <span v-if="step.state === 'active'" class="spinner"></span>
            <span v-else-if="step.state === 'done'">✓</span>
            <span v-else-if="step.state === 'failed'">!</span>
          </span>
          <span class="text">
            <strong>{{ step.title }}</strong>
            <span v-if="step.detail" class="muted small">{{ step.detail }}</span>
            <span v-if="step.key === 'analyze' && step.state === 'active'" class="bar">
              <span :style="{ width: `${(100 * done) / Math.max(1, total)}%` }"></span>
            </span>
          </span>
        </li>
      </ol>

      <div v-if="stage === 'error'" class="error-box" role="alert">
        <p>{{ error }}</p>
        <div class="actions">
          <button class="btn ghost" type="button" @click="emit('cancel')">Voltar</button>
          <button class="btn" type="button" @click="emit('generate')">Tentar de novo</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LimitPicker from './LimitPicker.vue'

export type Stage = 'idle' | 'download' | 'analyze' | 'build' | 'done' | 'error'

const props = defineProps<{
  nick: string
  limit: number
  stage: Stage
  failedAt: Stage | null
  found: number
  imported: number
  done: number
  total: number
  error: string
}>()
const emit = defineEmits<{ generate: []; cancel: []; 'update:limit': [value: number] }>()

const order: Stage[] = ['download', 'analyze', 'build']

const steps = computed(() => {
  const current = props.stage === 'error' ? props.failedAt ?? 'download' : props.stage
  const idx = order.indexOf(current)
  const state = (i: number) =>
    props.stage === 'error' && i === idx ? 'failed' : i < idx || props.stage === 'done' ? 'done' : i === idx ? 'active' : 'pending'

  return [
    {
      key: 'download',
      title: `Baixar as últimas ${props.limit} partidas do Chess.com`,
      detail: idx > 0 ? `${props.found} partidas encontradas, ${props.imported} novas` : '',
      state: state(0),
    },
    {
      key: 'analyze',
      title: 'Analisar cada lance com o Stockfish',
      detail: idx >= 1 ? `${props.done} de ${props.total} partidas` : '',
      state: state(1),
    },
    { key: 'build', title: 'Montar as estatísticas', detail: '', state: state(2) },
  ]
})
</script>

<style scoped>
.generate { display: grid; place-items: center; min-height: calc(100vh - var(--topbar-h, 64px) - 4rem); }

.box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  width: min(560px, 100%);
  padding: 2.5rem 2.25rem;
  text-align: center;
  box-shadow: var(--shadow);
}
.box h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
.box p { margin: 0; }
.icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  font-size: 1.8rem;
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 16px;
}
.btn.big { width: 100%; padding: 0.85rem 1.25rem; font-size: 1rem; }
.small { font-size: 0.82rem; }

.progress { align-items: stretch; text-align: left; }
.progress h1, .progress > p { text-align: center; }

.steps { display: flex; flex-direction: column; gap: 0; margin: 0.5rem 0 0; padding: 0; list-style: none; }
.step { position: relative; display: flex; gap: 0.9rem; padding: 0.7rem 0; }
.step:not(:last-child)::after {
  content: '';
  position: absolute;
  left: 13px;
  top: 2.6rem;
  bottom: -0.2rem;
  width: 2px;
  background: var(--border);
}
.marker {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  font-size: 0.85rem;
  font-weight: 800;
  color: var(--muted);
  background: var(--surface-2);
  border: 2px solid var(--border);
  border-radius: 50%;
}
.step.active .marker { border-color: var(--primary); background: var(--surface); }
.step.done .marker { color: #fff; background: var(--win); border-color: var(--win); }
.step.failed .marker { color: #fff; background: var(--loss); border-color: var(--loss); }
.marker .spinner { width: 14px; height: 14px; border-width: 2px; }
.text { display: flex; flex-direction: column; gap: 0.2rem; flex: 1; padding-top: 0.15rem; }
.step.pending strong { color: var(--muted); font-weight: 500; }
.bar { display: block; height: 6px; margin-top: 0.4rem; background: var(--track); border-radius: 99px; overflow: hidden; }
.bar span { display: block; height: 100%; background: var(--primary); border-radius: 99px; transition: width 0.4s ease; }

.error-box { padding: 0.9rem 1rem; color: var(--loss); background: var(--loss-soft); border-radius: 10px; }
.error-box p { margin: 0 0 0.75rem; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
</style>
