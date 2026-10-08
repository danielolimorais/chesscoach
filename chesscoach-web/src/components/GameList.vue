<template>
  <aside class="game-list" aria-label="Partidas analisadas">
    <div class="head">
      <h2>Partidas</h2>
      <span class="count">{{ filtered.length }}</span>
    </div>

    <div class="filters" role="group" aria-label="Filtrar por resultado">
      <button
        v-for="f in filters"
        :key="f.value"
        type="button"
        :class="['chip', { on: filter === f.value }]"
        :aria-pressed="filter === f.value"
        @click="filter = f.value"
      >
        {{ f.label }}
      </button>
    </div>

    <ul class="list">
      <li v-for="g in filtered" :key="g.id">
        <button
          type="button"
          :class="['row', { active: g.id === selectedId }]"
          :aria-current="g.id === selectedId ? 'true' : undefined"
          @click="emit('select', g.id)"
        >
          <span class="dot" :class="g.color" :title="`Você jogou de ${colorLabel(g.color).toLowerCase()}`"></span>
          <span class="main">
            <span class="opp">
              {{ g.opp_name || 'Desconhecido' }}
              <small v-if="g.opp_rating">{{ g.opp_rating }}</small>
            </span>
            <span class="meta">{{ timeClassLabel(g.time_class) }} · {{ formatDate(g.played_at) }}</span>
          </span>
          <span class="right">
            <span class="result" :class="g.result" :title="resultLabel[g.result]">{{ resultShort[g.result] }}</span>
            <span v-if="g.accuracy !== null" class="acc" title="Sua precisão na partida">{{ num(g.accuracy) }}%</span>
          </span>
        </button>
      </li>
    </ul>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { GameSummary, Result } from '../api'
import { colorLabel, formatDate, num, resultLabel, resultShort, timeClassLabel } from '../format'

const props = defineProps<{ games: GameSummary[]; selectedId: string | null }>()
const emit = defineEmits<{ select: [id: string] }>()

const filters = [
  { value: 'all', label: 'Todas' },
  { value: 'win', label: 'Vitórias' },
  { value: 'loss', label: 'Derrotas' },
  { value: 'draw', label: 'Empates' },
] as const
const filter = ref<'all' | Result>('all')

const filtered = computed(() =>
  filter.value === 'all' ? props.games : props.games.filter((g) => g.result === filter.value),
)
</script>

<style scoped>
.game-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.head { display: flex; align-items: center; justify-content: space-between; padding: 0 0.25rem; }
.head h2 { font-size: 0.95rem; }
.count {
  min-width: 1.6rem;
  padding: 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  text-align: center;
  color: var(--muted);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 99px;
}

.filters { display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.75rem 0; padding: 0 0.25rem; }
.chip {
  padding: 0.22rem 0.65rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 99px;
  cursor: pointer;
}
.chip:hover { color: var(--strong); background: var(--hover); }
.chip.on { color: #fff; background: var(--primary); border-color: var(--primary); }

.list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 0 0.25rem 0 0;
  list-style: none;
  overflow-y: auto;
}

.row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  width: 100%;
  padding: 0.6rem 0.65rem;
  text-align: left;
  color: inherit;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
}
.row:hover { background: var(--hover); }
.row.active { background: var(--primary-soft); border-color: color-mix(in srgb, var(--primary) 45%, transparent); }

.dot { flex-shrink: 0; width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--muted); }
.dot.white { background: #fff; }
.dot.black { background: #1f2430; }

.main { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.opp {
  overflow: hidden;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--strong);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.opp small { margin-left: 0.25rem; font-weight: 500; color: var(--muted); }
.meta { font-size: 0.76rem; color: var(--muted); }

.right { display: flex; flex-direction: column; align-items: flex-end; gap: 0.15rem; flex-shrink: 0; }
.result {
  display: grid;
  place-items: center;
  width: 1.4rem;
  height: 1.4rem;
  font-size: 0.72rem;
  font-weight: 800;
  border-radius: 6px;
}
.result.win { color: var(--win); background: var(--win-soft); }
.result.loss { color: var(--loss); background: var(--loss-soft); }
.result.draw { color: var(--muted); background: var(--draw-soft); }
.acc { font-size: 0.72rem; font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums; }
</style>
