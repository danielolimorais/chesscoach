<template>
  <div class="search-screen">
    <div class="hero">
      <div class="brand"><span class="logo" aria-hidden="true">♞</span> ChessCoach</div>
      <h1>Descubra onde você perde pontos.</h1>
      <p class="lead">
        Buscamos suas últimas {{ limit }} partidas no Chess.com, analisamos cada lance com o Stockfish
        e mostramos seus padrões de erro, aberturas e as posições que mais vale a pena treinar.
      </p>

      <form class="search" @submit.prevent="submit">
        <label class="sr-only" for="nick">Nick no Chess.com</label>
        <input
          id="nick"
          v-model="nick"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="Seu nick no Chess.com"
          :disabled="loading"
        />
        <button class="btn" type="submit" :disabled="loading || !nick.trim()">
          <span v-if="loading" class="spinner light" aria-hidden="true"></span>
          {{ loading ? 'Buscando…' : 'Analisar partidas' }}
        </button>
      </form>

      <p v-if="loading" class="status" role="status">{{ step }}</p>
      <p v-else-if="error" class="error" role="alert">{{ error }}</p>

      <ul class="features">
        <li><strong>Precisão e ACPL</strong><span>por cor, fase da partida e ritmo</span></li>
        <li><strong>Padrões de erro</strong><span>abertura, meio-jogo, final e pressão de tempo</span></li>
        <li><strong>Posições para treinar</strong><span>os lances que mais custaram pontos</span></li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ loading: boolean; step: string; error: string; initialNick?: string; limit: number }>()
const emit = defineEmits<{ submit: [nick: string] }>()

const nick = ref(props.initialNick ?? '')

function submit() {
  if (nick.value.trim()) emit('submit', nick.value.trim())
}
</script>

<style scoped>
.search-screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem 1.25rem;
  background:
    radial-gradient(1200px 500px at 50% -10%, color-mix(in srgb, var(--primary) 12%, transparent), transparent 70%),
    var(--bg);
}

.hero {
  width: min(640px, 100%);
  text-align: center;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 1.75rem;
  padding: 0.35rem 0.85rem;
  font-weight: 700;
  color: var(--strong);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 99px;
  box-shadow: var(--shadow-sm);
}
.logo { font-size: 1.15rem; line-height: 1; }

h1 {
  font-size: clamp(2rem, 5vw, 3.1rem);
  font-weight: 800;
  letter-spacing: -0.03em;
}

.lead {
  margin: 1rem auto 2rem;
  max-width: 520px;
  font-size: 1.05rem;
  color: var(--muted);
}

.search {
  display: flex;
  gap: 0.5rem;
  padding: 0.4rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: var(--shadow);
}
.search input {
  flex: 1;
  min-width: 0;
  padding: 0.7rem 0.9rem;
  font: inherit;
  font-size: 1rem;
  color: var(--strong);
  background: transparent;
  border: 0;
  outline: none;
}
.search .btn { padding: 0.7rem 1.25rem; }
.spinner.light { width: 15px; height: 15px; border-color: rgba(255, 255, 255, 0.35); border-top-color: #fff; }

.status { margin: 1rem 0 0; color: var(--muted); }
.error { margin: 1rem 0 0; color: var(--loss); font-weight: 500; }

.features {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
  margin: 2.5rem 0 0;
  padding: 0;
  list-style: none;
  text-align: left;
}
.features li {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.9rem 1rem;
  font-size: 0.85rem;
  background: color-mix(in srgb, var(--surface) 70%, transparent);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.features strong { color: var(--strong); font-size: 0.9rem; }
.features span { color: var(--muted); }

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

@media (max-width: 640px) {
  .search { flex-direction: column; }
  .features { grid-template-columns: 1fr; }
}
</style>
