<template>
  <div class="report">
    <header class="head">
      <div>
        <h1>Suas últimas {{ report.total_games }} partidas</h1>
        <p class="muted">
          Gerado em {{ formatDateTime(report.generated_at) }} · {{ report.analyzed_games }} partidas analisadas pelo
          Stockfish
        </p>
      </div>
      <div class="head-actions">
        <LimitPicker :model-value="limit" @update:model-value="emit('update:limit', $event)" />
        <button class="btn" type="button" @click="emit('regenerate')">Gerar novo relatório</button>
      </div>
    </header>

    <!-- ===================== RESULTADOS ===================== -->
    <section class="card section results">
      <div class="totals">
        <div v-for="t in totals" :key="t.key" class="total">
          <span class="total-label"><span class="sw" :class="t.key"></span>{{ t.label }}</span>
          <strong>{{ t.count }}</strong>
          <span class="muted">{{ pct(t.pct) }}</span>
        </div>
        <div class="total score">
          <span class="total-label">Aproveitamento</span>
          <strong>{{ pct(r.overall.score_pct) }}</strong>
          <span class="muted">dos pontos</span>
        </div>
      </div>

      <div class="splits">
        <div v-for="row in splitRows" :key="row.label" class="split">
          <span class="split-label">{{ row.label }}</span>
          <WdlBar :stats="row.stats" />
          <span class="split-nums">{{ row.stats.wins }} · {{ row.stats.draws }} · {{ row.stats.losses }}</span>
        </div>
        <p class="legend muted">
          <span><span class="sw win"></span>Vitórias</span>
          <span><span class="sw draw"></span>Empates</span>
          <span><span class="sw loss"></span>Derrotas</span>
        </p>
      </div>
    </section>

    <div class="two">
      <!-- ===================== ABERTURAS ===================== -->
      <section class="card section">
        <div class="section-head">
          <h2>Aberturas mais jogadas</h2>
          <span class="muted small">V · E · D</span>
        </div>
        <ul class="openings">
          <li v-for="o in visibleOpenings" :key="`${o.name}-${o.color}`" class="opening">
            <span class="op-name">
              <span class="dot" :class="o.color" :title="`Você de ${colorLabel(o.color).toLowerCase()}`"></span>
              <span class="name" :title="o.name">{{ o.name }}</span>
              <span class="games muted">{{ o.games }} {{ o.games === 1 ? 'jogo' : 'jogos' }}</span>
            </span>
            <WdlBar :stats="o" />
            <span class="op-rates">
              <span class="win">{{ pct(rate(o.wins, o.games)) }}</span>
              <span class="draw">{{ pct(rate(o.draws, o.games)) }}</span>
              <span class="loss">{{ pct(rate(o.losses, o.games)) }}</span>
            </span>
          </li>
        </ul>
        <button v-if="report.openings.length > 6" class="link" type="button" @click="showAllOpenings = !showAllOpenings">
          {{ showAllOpenings ? 'Mostrar menos' : `Ver todas (${report.openings.length})` }}
        </button>
      </section>

      <!-- ===================== ERROS ===================== -->
      <section class="card section">
        <div class="section-head">
          <h2>Erros mais cometidos</h2>
          <span class="muted small">{{ seriousTotal }} erros graves</span>
        </div>

        <ul v-if="report.error_types.length" class="errors">
          <li v-for="e in report.error_types" :key="e.key" class="err">
            <span class="err-top">
              <span class="err-label" :class="{ other: e.key === 'other' }">{{ e.label }}</span>
              <span class="err-count">{{ e.count }}</span>
            </span>
            <span class="track"><span class="fill" :class="{ other: e.key === 'other' }" :style="{ width: `${e.share}%` }"></span></span>
          </li>
        </ul>
        <p v-else class="muted">Nenhum erro grave nestas partidas. 👏</p>

        <div class="phases">
          <span class="eyebrow">Por fase da partida</span>
          <div class="phase-row">
            <div v-for="p in report.phases" :key="p.phase" class="phase" :title="`${num(p.error_rate)} erros graves a cada 100 lances`">
              <strong>{{ p.mistakes + p.blunders }}</strong>
              <span class="muted">{{ phaseLabel[p.phase] }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ===================== POSIÇÕES ===================== -->
    <section v-if="report.top_mistakes.length" class="card section">
      <div class="section-head">
        <h2>Posições para treinar</h2>
        <span class="muted small">Clique para abrir a partida neste lance</span>
      </div>
      <div class="positions">
        <button
          v-for="m in visiblePositions"
          :key="`${m.game_id}-${m.ply}`"
          type="button"
          class="position"
          @click="emit('open-game', m.game_id, m.ply)"
        >
          <ChessBoard :fen="m.fen_before" :orientation="m.color" :arrows="arrowsFor(m.played_uci, m.best_uci)" small />
          <span class="pos-info">
            <span class="pos-top">
              <span class="pos-cat">{{ m.category_label }}</span>
              <span class="drop">−{{ num(m.win_drop, 0) }}%</span>
            </span>
            <span class="pos-moves">
              <b class="bad">{{ m.played_move }}</b> <span class="muted">→</span> <b class="good">{{ m.best_move }}</b>
            </span>
            <span class="muted small">vs {{ m.opp_name }} · lance {{ m.move_number }}</span>
          </span>
        </button>
      </div>
      <button v-if="report.top_mistakes.length > 4" class="link" type="button" @click="showAllPositions = !showAllPositions">
        {{ showAllPositions ? 'Mostrar menos' : `Ver mais ${report.top_mistakes.length - 4}` }}
      </button>
    </section>

    <!-- ===================== DETALHES ===================== -->
    <details class="card more">
      <summary>
        <span>Mais estatísticas</span>
        <span class="muted small">precisão, diagnóstico, pressão de tempo e rating</span>
      </summary>

      <div class="more-body">
        <div class="kpis">
          <div class="kpi">
            <span class="eyebrow">Precisão</span>
            <strong>{{ pct(q.accuracy, 1) }}</strong>
            <span class="muted small">Brancas {{ pct(q.accuracy_white, 1) }} · Pretas {{ pct(q.accuracy_black, 1) }}</span>
          </div>
          <div class="kpi">
            <span class="eyebrow">ACPL</span>
            <strong>{{ num(q.acpl, 0) }}</strong>
            <span class="muted small">perda média por lance</span>
          </div>
          <div class="kpi">
            <span class="eyebrow">Blunders por partida</span>
            <strong>{{ num(q.blunders_per_game) }}</strong>
            <span class="muted small">{{ q.blunders }} no total</span>
          </div>
          <div class="kpi">
            <span class="eyebrow">Vantagens desperdiçadas</span>
            <strong>{{ report.advantage.wasted }}</strong>
            <span class="muted small">chegou a +3 e não venceu</span>
          </div>
        </div>

        <div class="more-grid">
          <div>
            <h3>Diagnóstico</h3>
            <ul v-if="report.insights.length" class="insights">
              <li v-for="(text, i) in report.insights" :key="i">{{ text }}</li>
            </ul>
            <p v-else class="muted small">Nenhum padrão forte apareceu nestas partidas.</p>

            <h3 class="mt">Pressão de tempo</h3>
            <p class="small">
              Com tempo: <b>{{ num(tp.error_rate_normal) }}</b> erros graves a cada 100 lances.
              Com pouco tempo: <b>{{ tp.moves ? num(tp.error_rate_pressure) : '–' }}</b>.
              <span class="muted">({{ pct(tp.share_of_moves, 1) }} dos lances foram com menos de 10% do relógio.)</span>
            </p>
          </div>
          <div>
            <h3>Rating em {{ timeClassLabel(report.rating.time_class).toLowerCase() }}</h3>
            <RatingChart :points="report.rating.history" />
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Report, ResultStats } from '../api'
import { colorLabel, num, pct, phaseLabel, timeClassLabel, uciToSquares } from '../format'
import ChessBoard, { type Arrow } from './ChessBoard.vue'
import LimitPicker from './LimitPicker.vue'
import RatingChart from './RatingChart.vue'
import WdlBar from './WdlBar.vue'

const props = defineProps<{ report: Report; limit: number }>()
const emit = defineEmits<{
  'open-game': [id: string, ply?: number]
  regenerate: []
  'update:limit': [value: number]
}>()

const r = computed(() => props.report.results)
const q = computed(() => props.report.quality)
const tp = computed(() => props.report.time_pressure)

const showAllOpenings = ref(false)
const showAllPositions = ref(false)

const rate = (part: number, total: number) => (total ? (100 * part) / total : 0)

const totals = computed(() => {
  const o = r.value.overall
  return [
    { key: 'win', label: 'Vitórias', count: o.wins, pct: rate(o.wins, o.games) },
    { key: 'draw', label: 'Empates', count: o.draws, pct: rate(o.draws, o.games) },
    { key: 'loss', label: 'Derrotas', count: o.losses, pct: rate(o.losses, o.games) },
  ]
})

const splitRows = computed(() => {
  const rows: { label: string; stats: ResultStats }[] = [
    { label: 'Brancas', stats: r.value.white },
    { label: 'Pretas', stats: r.value.black },
  ]
  for (const [tc, stats] of Object.entries(r.value.by_time_class)) {
    if (stats.games >= 2) rows.push({ label: timeClassLabel(tc), stats })
  }
  return rows
})

const visibleOpenings = computed(() => (showAllOpenings.value ? props.report.openings : props.report.openings.slice(0, 6)))
const visiblePositions = computed(() =>
  showAllPositions.value ? props.report.top_mistakes : props.report.top_mistakes.slice(0, 4),
)
const seriousTotal = computed(() => q.value.blunders + q.value.mistakes)

function formatDateTime(value: string) {
  const d = new Date(value)
  return Number.isNaN(d.getTime())
    ? '–'
    : d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function arrowsFor(played: string | null, best: string | null): Arrow[] {
  const arrows: Arrow[] = []
  const p = uciToSquares(played)
  const b = uciToSquares(best)
  if (p) arrows.push({ from: p[0], to: p[1], brush: 'red' })
  if (b && best !== played) arrows.push({ from: b[0], to: b[1], brush: 'green' })
  return arrows
}
</script>

<style scoped>
.report { display: flex; flex-direction: column; gap: 1.25rem; max-width: 1400px; margin: 0 auto; }

.head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 1rem; }
.head h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }
.head p { margin: 0.3rem 0 0; font-size: 0.88rem; }
.head-actions { display: flex; align-items: center; gap: 0.6rem; }

.section { display: flex; flex-direction: column; gap: 1rem; padding: 1.5rem 1.6rem; min-width: 0; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.section h2 { font-size: 1.05rem; font-weight: 700; }
.small { font-size: 0.8rem; }

.link {
  align-self: flex-start;
  padding: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--primary);
  background: none;
  border: 0;
  cursor: pointer;
}
.link:hover { text-decoration: underline; }

.sw { display: inline-block; width: 10px; height: 10px; margin-right: 0.4rem; border-radius: 3px; }
.sw.win { background: var(--win); }
.sw.draw { background: var(--draw); }
.sw.loss { background: var(--loss); }

/* resultados */
.results { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 2rem; align-items: center; }
.totals { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; }
.total { display: flex; flex-direction: column; gap: 0.15rem; }
.total-label { display: flex; align-items: center; font-size: 0.82rem; font-weight: 600; color: var(--muted); }
.total strong { font-size: 2.4rem; font-weight: 700; line-height: 1.1; letter-spacing: -0.03em; color: var(--strong); }
.total.score { padding-left: 1rem; border-left: 1px solid var(--border); }
.total.score strong { color: var(--primary); }

.splits { display: flex; flex-direction: column; gap: 0.6rem; }
.split { display: grid; grid-template-columns: 4.5rem minmax(0, 1fr) 4.5rem; align-items: center; gap: 0.75rem; }
.split-label { font-size: 0.85rem; font-weight: 600; color: var(--strong); }
.split-nums { font-size: 0.82rem; color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.legend { display: flex; gap: 1rem; margin: 0.2rem 0 0; font-size: 0.75rem; }
.legend span { display: inline-flex; align-items: center; }

.two { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 1.25rem; align-items: start; }

/* aberturas */
.openings { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.opening {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(64px, 110px) 7.6rem;
  align-items: center;
  gap: 1rem;
  padding: 0.7rem 0;
  border-bottom: 1px solid var(--border);
}
.opening:last-child { border-bottom: 0; }
.op-name { display: flex; align-items: center; gap: 0.55rem; min-width: 0; }
.name { overflow: hidden; font-size: 0.9rem; font-weight: 600; color: var(--strong); white-space: nowrap; text-overflow: ellipsis; }
.games { flex-shrink: 0; font-size: 0.76rem; }
.op-rates { display: grid; grid-template-columns: repeat(3, 1fr); font-size: 0.8rem; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.op-rates .win { color: var(--win); }
.op-rates .draw { color: var(--muted); }
.op-rates .loss { color: var(--loss); }
.dot { flex-shrink: 0; width: 11px; height: 11px; border-radius: 50%; border: 2px solid var(--muted); }
.dot.white { background: #fff; }
.dot.black { background: #1f2430; }

/* erros */
.errors { display: flex; flex-direction: column; gap: 0.85rem; margin: 0; padding: 0; list-style: none; }
.err { display: flex; flex-direction: column; gap: 0.35rem; }
.err-top { display: flex; justify-content: space-between; align-items: baseline; }
.err-label { font-size: 0.9rem; font-weight: 600; color: var(--strong); }
.err-label.other { color: var(--muted); font-weight: 500; }
.err-count { font-size: 0.95rem; font-weight: 700; color: var(--strong); font-variant-numeric: tabular-nums; }
.track { display: block; height: 8px; background: var(--track); border-radius: 4px; overflow: hidden; }
.fill { display: block; height: 100%; background: var(--series-1); border-radius: 4px; }
.fill.other { background: var(--draw); }

.phases { display: flex; flex-direction: column; gap: 0.6rem; padding-top: 1rem; border-top: 1px solid var(--border); }
.phase-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }
.phase { display: flex; flex-direction: column; padding: 0.65rem 0.8rem; background: var(--surface-2); border-radius: 10px; }
.phase strong { font-size: 1.35rem; color: var(--strong); }
.phase .muted { font-size: 0.8rem; }

/* posições */
.positions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; }
.position {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 0.55rem;
  text-align: left;
  color: inherit;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.position:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); box-shadow: var(--shadow); }
.pos-info { display: flex; flex-direction: column; gap: 0.2rem; padding: 0 0.2rem 0.2rem; }
.pos-top { display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; }
.pos-cat { font-size: 0.8rem; font-weight: 600; color: var(--strong); }
.drop { font-size: 0.8rem; font-weight: 700; color: var(--loss); }
.pos-moves { font-size: 0.95rem; }
.bad { color: var(--loss); }
.good { color: var(--good); }

/* detalhes recolhidos */
.more { padding: 0; }
.more summary {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 1.1rem 1.6rem;
  font-weight: 700;
  color: var(--strong);
  list-style: none;
  cursor: pointer;
}
.more summary::-webkit-details-marker { display: none; }
.more summary::before { content: '▸'; color: var(--muted); transition: transform 0.15s ease; }
.more[open] summary::before { transform: rotate(90deg); }
.more summary .muted { font-weight: 400; }
.more-body { display: flex; flex-direction: column; gap: 1.5rem; padding: 0 1.6rem 1.6rem; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; }
.kpi { display: flex; flex-direction: column; gap: 0.2rem; padding: 0.9rem 1rem; background: var(--surface-2); border-radius: 12px; }
.kpi strong { font-size: 1.6rem; color: var(--strong); }
.more-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 2rem; }
.more-grid h3 { margin-bottom: 0.6rem; font-size: 0.95rem; }
.mt { margin-top: 1.25rem; }
.insights { display: flex; flex-direction: column; gap: 0.5rem; margin: 0; padding-left: 1.1rem; font-size: 0.88rem; color: var(--strong); }

@media (max-width: 1200px) {
  .results { grid-template-columns: minmax(0, 1fr); gap: 1.5rem; }
  .two { grid-template-columns: minmax(0, 1fr); }
  .positions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .total.score { padding-left: 0; border-left: 0; }
  .opening { grid-template-columns: minmax(0, 1fr) 7.5rem; }
  .opening :deep(.wdl) { display: none; }
  .kpis, .more-grid { grid-template-columns: minmax(0, 1fr); }
  .head-actions { width: 100%; flex-wrap: wrap; }
}
</style>
