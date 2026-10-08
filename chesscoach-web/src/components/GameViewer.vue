<template>
  <div class="viewer">
    <div v-if="loading" class="state card" role="status">
      <span class="spinner big" aria-hidden="true"></span>
      <p>Carregando a análise da partida…</p>
      <p class="muted small">Se ela ainda não foi analisada, o Stockfish leva alguns segundos.</p>
    </div>

    <div v-else-if="error" class="state card" role="alert">
      <h2>Não foi possível abrir a partida</h2>
      <p class="muted">{{ error }}</p>
      <div class="row-btns">
        <button class="btn ghost" type="button" @click="emit('back')">← Voltar ao relatório</button>
        <button class="btn" type="button" @click="load">Tentar novamente</button>
      </div>
    </div>

    <div v-else-if="data && current" class="layout">
      <!-- tabuleiro + barra de avaliação -->
      <div class="board-col">
        <div class="board-wrap">
          <div
            class="evalbar"
            :class="{ flipped: data.game.color === 'black' }"
            role="img"
            :aria-label="`Avaliação: ${current.eval_text}`"
            :title="`Avaliação antes do lance: ${current.eval_text}`"
          >
            <span class="evalbar-white" :style="{ height: `${whitePct}%` }"></span>
            <span class="evalbar-text" :class="{ top: evalOnTop, 'on-white': whitePct >= 50 }">{{ shortEval }}</span>
          </div>
          <ChessBoard
            :fen="current.fen_before"
            :orientation="data.game.color"
            :last-move="lastMove"
            :arrows="arrows"
          />
        </div>
      </div>

      <!-- painel lateral -->
      <aside class="side card">
        <div class="side-head">
          <button class="link" type="button" @click="emit('back')">← Relatório</button>
          <a v-if="data.game.url" class="link" :href="data.game.url" target="_blank" rel="noopener">
            Abrir no Chess.com ↗
          </a>
        </div>

        <div class="game-title">
          <h2>
            vs {{ data.game.opp_name || 'Desconhecido' }}
            <small v-if="data.game.opp_rating">{{ data.game.opp_rating }}</small>
          </h2>
          <span class="badge" :class="data.game.result">{{ resultLabel[data.game.result] }}</span>
        </div>
        <p class="game-meta muted">
          {{ colorLabel(data.game.color) }} · {{ timeClassLabel(data.game.time_class) }} ·
          {{ formatDateLong(data.game.played_at) }}
          <template v-if="data.game.opening_name"><br />{{ data.game.opening_name }}</template>
        </p>

        <div class="chips">
          <span class="chip-stat"><b>{{ pct(data.summary.accuracy, 1) }}</b> precisão</span>
          <span class="chip-stat"><b>{{ num(data.summary.acpl, 0) }}</b> ACPL</span>
          <span class="chip-stat blunder"><b>{{ data.summary.blunders }}</b> blunders</span>
          <span class="chip-stat mistake"><b>{{ data.summary.mistakes }}</b> erros</span>
          <span class="chip-stat inaccuracy"><b>{{ data.summary.inaccuracies }}</b> imprecisões</span>
        </div>

        <!-- lance atual -->
        <div class="current">
          <div class="current-head">
            <span class="badge" :class="current.severity">{{ severityLabel[current.severity] }}</span>
            <span class="muted small">
              {{ current.is_user ? 'Seu lance' : 'Lance do adversário' }}
              <template v-if="current.clock_seconds !== null"> · ⏱ {{ formatClock(current.clock_seconds) }}</template>
            </span>
          </div>
          <h3>Lance {{ current.move_number }}{{ current.color === 'black' ? '…' : '.' }} {{ current.played_move }}</h3>
          <div class="moves">
            <div class="mv" :class="{ bad: isError(current.severity) }">
              <span class="eyebrow">Jogado</span>
              <strong>{{ current.played_move }}</strong>
            </div>
            <div class="mv good">
              <span class="eyebrow">Melhor</span>
              <strong>{{ current.best_move || current.played_move }}</strong>
            </div>
          </div>
          <p class="verdict">
            <template v-if="isError(current.severity)">
              Custou <b>{{ num(current.win_drop, 0) }}%</b> de chance de vitória ({{ current.cp_loss }} cp).
            </template>
            <template v-else-if="current.severity === 'best'">Exatamente o lance do Stockfish.</template>
            <template v-else>Lance sólido: a avaliação quase não mudou.</template>
          </p>
        </div>

        <!-- navegação -->
        <div class="nav">
          <div class="seg" role="group" aria-label="Modo de navegação">
            <button type="button" :class="{ on: mode === 'errors' }" @click="mode = 'errors'">
              Seus erros ({{ userErrors.length }})
            </button>
            <button type="button" :class="{ on: mode === 'all' }" @click="mode = 'all'">Todos os lances</button>
          </div>
          <div class="nav-btns">
            <button class="btn ghost" type="button" :disabled="prevIndex === null" @click="go(prevIndex)">← Anterior</button>
            <button class="btn" type="button" :disabled="nextIndex === null" @click="go(nextIndex)">Próximo →</button>
          </div>
          <p class="muted tiny">Use as setas ← → do teclado.</p>
        </div>

        <!-- lista de lances -->
        <ol ref="listRef" class="movelist" aria-label="Lances da partida">
          <li v-for="row in moveRows" :key="row.number">
            <span class="num">{{ row.number }}.</span>
            <button
              v-for="i in row.indices"
              :key="i"
              type="button"
              :data-index="i"
              :class="['m', data.moves[i].severity, { on: i === index, mine: data.moves[i].is_user }]"
              @click="go(i)"
            >
              {{ data.moves[i].played_move }}
            </button>
          </li>
        </ol>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, type GameAnalysis } from '../api'
import {
  colorLabel,
  formatClock,
  formatDateLong,
  isError,
  num,
  pct,
  resultLabel,
  severityLabel,
  timeClassLabel,
  uciToSquares,
} from '../format'
import ChessBoard, { type Arrow } from './ChessBoard.vue'

const props = defineProps<{ gameId: string; initialPly?: number | null }>()
const emit = defineEmits<{ back: []; analyzed: [] }>()

const data = ref<GameAnalysis | null>(null)
const loading = ref(false)
const error = ref('')
const index = ref(0)
const mode = ref<'errors' | 'all'>('errors')
const listRef = ref<HTMLElement | null>(null)
let requestId = 0

async function load() {
  const myId = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await api.game(props.gameId)
    if (myId !== requestId) return
    data.value = result
    const fromPly = props.initialPly ? result.moves.findIndex((m) => m.ply === props.initialPly) : -1
    const firstError = result.moves.findIndex((m) => m.is_user && isError(m.severity))
    index.value = fromPly >= 0 ? fromPly : Math.max(0, firstError)
    mode.value = firstError >= 0 ? 'errors' : 'all'
    emit('analyzed')
  } catch (e) {
    if (myId === requestId) error.value = (e as Error).message
  } finally {
    if (myId === requestId) loading.value = false
  }
}

watch(() => [props.gameId, props.initialPly], load, { immediate: true })

const current = computed(() => data.value?.moves[index.value])
const userErrors = computed(() =>
  (data.value?.moves ?? []).flatMap((m, i) => (m.is_user && isError(m.severity) ? [i] : [])),
)

const prevIndex = computed<number | null>(() => {
  if (mode.value === 'all') return index.value > 0 ? index.value - 1 : null
  const prev = userErrors.value.filter((i) => i < index.value)
  return prev.length ? prev[prev.length - 1] : null
})
const nextIndex = computed<number | null>(() => {
  const total = data.value?.moves.length ?? 0
  if (mode.value === 'all') return index.value < total - 1 ? index.value + 1 : null
  return userErrors.value.find((i) => i > index.value) ?? null
})

function go(i: number | null) {
  if (i !== null) index.value = i
}

const lastMove = computed(() =>
  data.value && index.value > 0 ? uciToSquares(data.value.moves[index.value - 1].played_uci) : null,
)

const arrows = computed<Arrow[]>(() => {
  const m = current.value
  if (!m) return []
  const out: Arrow[] = []
  const played = uciToSquares(m.played_uci)
  const best = uciToSquares(m.best_uci)
  if (played) out.push({ from: played[0], to: played[1], brush: isError(m.severity) ? 'red' : 'blue' })
  if (best && m.best_uci !== m.played_uci) out.push({ from: best[0], to: best[1], brush: 'green' })
  return out
})

// Barra de avaliação: % de vitória das brancas (mesma curva usada no backend).
const whitePct = computed(() => {
  const cp = current.value?.eval_before
  if (cp === null || cp === undefined) return 50
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1)
})
const shortEval = computed(() => (current.value?.eval_text ?? '').replace(/^\+/, ''))
// O número aparece no lado de quem está melhor.
const evalOnTop = computed(() => {
  const whiteBetter = whitePct.value >= 50
  return data.value?.game.color === 'black' ? whiteBetter : !whiteBetter
})

// Linhas "1. e4 e5" da lista de lances.
const moveRows = computed(() => {
  const rows: { number: number; indices: number[] }[] = []
  ;(data.value?.moves ?? []).forEach((m, i) => {
    const last = rows[rows.length - 1]
    if (last && last.number === m.move_number) last.indices.push(i)
    else rows.push({ number: m.move_number, indices: [i] })
  })
  return rows
})

// Mantém o lance atual visível dentro da lista (sem rolar a página inteira).
watch(index, async () => {
  await nextTick()
  const list = listRef.value
  const el = list?.querySelector<HTMLElement>(`[data-index="${index.value}"]`)
  if (!list || !el) return
  const top = el.offsetTop - list.offsetTop
  if (top < list.scrollTop || top > list.scrollTop + list.clientHeight - 40) {
    list.scrollTo({ top: top - list.clientHeight / 2, behavior: 'smooth' })
  }
})

function onKeydown(e: KeyboardEvent) {
  if (e.altKey || e.ctrlKey || e.metaKey) return
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (e.key === 'ArrowRight') {
    e.preventDefault()
    go(nextIndex.value)
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    go(prevIndex.value)
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.viewer { --board-max: calc(100vh - var(--topbar-h, 64px) - 3rem); }

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  min-height: 60vh;
  padding: 2rem;
  text-align: center;
}
.state p { margin: 0; }
.spinner.big { width: 34px; height: 34px; border-width: 3px; margin-bottom: 0.75rem; }
.row-btns { display: flex; gap: 0.5rem; margin-top: 1rem; }
.small { font-size: 0.82rem; }
.tiny { margin: 0; font-size: 0.75rem; text-align: center; }

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 400px);
  gap: 1.5rem;
  align-items: start;
}

.board-col { display: flex; justify-content: center; min-width: 0; }
.board-wrap {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 10px;
  width: min(100%, calc(var(--board-max) + 32px));
}

/* barra de avaliação */
.evalbar {
  position: relative;
  display: flex;
  flex-direction: column-reverse; /* branco embaixo quando você joga de brancas */
  overflow: hidden;
  background: #3a3a3a;
  border-radius: 6px;
}
.evalbar.flipped { flex-direction: column; }
.evalbar-white { display: block; width: 100%; background: #f2f2f2; transition: height 0.35s ease; }
.evalbar-text {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 4px;
  font-size: 0.6rem;
  font-weight: 700;
  text-align: center;
  color: #eee;
}
.evalbar-text.on-white { color: #333; }
.evalbar-text.top { top: 4px; bottom: auto; }

/* painel lateral */
.side {
  position: sticky;
  top: calc(var(--topbar-h, 64px) + 1.5rem);
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: var(--board-max);
  padding: 1.15rem 1.25rem;
  overflow: hidden;
}
.side-head { display: flex; justify-content: space-between; }
.link {
  padding: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--primary);
  text-decoration: none;
  background: none;
  border: 0;
  cursor: pointer;
}
.link:hover { text-decoration: underline; }

.game-title { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.game-title h2 { font-size: 1.2rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.game-title small { font-size: 0.85rem; font-weight: 500; color: var(--muted); }
.game-meta { margin: -0.6rem 0 0; font-size: 0.82rem; }

.chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.chip-stat {
  padding: 0.2rem 0.55rem;
  font-size: 0.76rem;
  color: var(--muted);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 99px;
}
.chip-stat b { color: var(--strong); font-variant-numeric: tabular-nums; }
.chip-stat.blunder b { color: var(--blunder); }
.chip-stat.mistake b { color: var(--mistake); }
.chip-stat.inaccuracy b { color: var(--inaccuracy); }

.current {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 0.9rem;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.current-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.current h3 { font-size: 1.15rem; }
.moves { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
.mv {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.55rem 0.7rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.mv strong { font-size: 1.35rem; letter-spacing: -0.01em; color: var(--strong); }
.mv.bad strong { color: var(--blunder); }
.mv.good strong { color: var(--good); }
.verdict { margin: 0; font-size: 0.85rem; }
.verdict b { color: var(--strong); }

.nav { display: flex; flex-direction: column; gap: 0.5rem; }
.seg { display: grid; grid-template-columns: 1fr 1fr; padding: 3px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; }
.seg button {
  padding: 0.4rem 0.5rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-radius: 7px;
  cursor: pointer;
}
.seg button.on { color: var(--strong); background: var(--surface); box-shadow: var(--shadow-sm); }
.nav-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }

/* lista de lances */
.movelist {
  flex: 1;
  min-height: 90px;
  margin: 0;
  padding: 0.35rem;
  overflow-y: auto;
  list-style: none;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.movelist li { display: grid; grid-template-columns: 2.4rem 1fr 1fr; align-items: center; }
.num { font-size: 0.78rem; color: var(--muted); text-align: right; padding-right: 0.5rem; font-variant-numeric: tabular-nums; }
.m {
  padding: 0.2rem 0.45rem;
  font-size: 0.85rem;
  text-align: left;
  color: var(--text);
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
}
.m:hover { background: var(--hover); }
.m.mine { font-weight: 600; color: var(--strong); }
.m.inaccuracy { color: var(--inaccuracy); }
.m.mistake { color: var(--mistake); }
.m.blunder { color: var(--blunder); }
.m.on { color: #fff; background: var(--primary); }

@media (max-width: 1000px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .side { position: static; max-height: none; }
  .movelist { max-height: 260px; }
}
</style>
