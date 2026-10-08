<template>
  <div ref="wrapRef" class="rating-chart">
    <p v-if="points.length < 2" class="muted empty">Poucas partidas para mostrar a evolução.</p>
    <template v-else>
      <svg
        :width="width"
        :height="height"
        role="img"
        :aria-label="`Rating de ${points[0].rating} a ${points[points.length - 1].rating}`"
        @mousemove="onMove"
        @mouseleave="hover = null"
      >
        <!-- linhas de grade horizontais (discretas) -->
        <g class="grid">
          <g v-for="t in ticks" :key="t">
            <line :x1="pad.l" :x2="width - pad.r" :y1="y(t)" :y2="y(t)" />
            <text :x="pad.l - 8" :y="y(t)" dy="0.32em" text-anchor="end">{{ t }}</text>
          </g>
        </g>
        <path class="area" :d="areaPath" />
        <path class="line" :d="linePath" />
        <circle class="end" :cx="x(points.length - 1)" :cy="y(points[points.length - 1].rating)" r="4.5" />
        <g v-if="hover !== null">
          <line class="cross" :x1="x(hover)" :x2="x(hover)" :y1="pad.t" :y2="height - pad.b" />
          <circle class="dot" :cx="x(hover)" :cy="y(points[hover].rating)" r="4.5" />
        </g>
      </svg>
      <div
        v-if="hover !== null"
        class="tooltip"
        :style="{ left: `${x(hover)}px`, top: `${y(points[hover].rating)}px` }"
      >
        <strong>{{ points[hover].rating }}</strong>
        <span>{{ formatDateLong(points[hover].date) }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatDateLong } from '../format'

const props = defineProps<{ points: { date: string; rating: number }[] }>()

const wrapRef = ref<HTMLElement | null>(null)
const width = ref(480)
const height = 240
const pad = { t: 14, r: 14, b: 14, l: 46 }
const hover = ref<number | null>(null)

let observer: ResizeObserver | null = null
onMounted(() => {
  if (!wrapRef.value) return
  observer = new ResizeObserver(([entry]) => {
    width.value = Math.max(240, Math.floor(entry.contentRect.width))
  })
  observer.observe(wrapRef.value)
})
onBeforeUnmount(() => observer?.disconnect())

const extent = computed(() => {
  const r = props.points.map((p) => p.rating)
  const lo = Math.min(...r)
  const hi = Math.max(...r)
  const step = hi - lo > 120 ? 50 : 25
  return { lo: Math.floor((lo - 5) / step) * step, hi: Math.ceil((hi + 5) / step) * step, step }
})

const ticks = computed(() => {
  const out: number[] = []
  for (let t = extent.value.lo; t <= extent.value.hi; t += extent.value.step) out.push(t)
  return out
})

const x = (i: number) => pad.l + (i / Math.max(1, props.points.length - 1)) * (width.value - pad.l - pad.r)
const y = (v: number) =>
  pad.t + (1 - (v - extent.value.lo) / (extent.value.hi - extent.value.lo || 1)) * (height - pad.t - pad.b)

const linePath = computed(() => props.points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.rating)}`).join(' '))
const areaPath = computed(
  () => `${linePath.value} L${x(props.points.length - 1)},${height - pad.b} L${x(0)},${height - pad.b} Z`,
)

function onMove(e: MouseEvent) {
  const rect = (e.currentTarget as SVGElement).getBoundingClientRect()
  const rel = (e.clientX - rect.left - pad.l) / (width.value - pad.l - pad.r)
  hover.value = Math.min(props.points.length - 1, Math.max(0, Math.round(rel * (props.points.length - 1))))
}
</script>

<style scoped>
.rating-chart { position: relative; width: 100%; }
svg { display: block; overflow: visible; }
.grid line { stroke: var(--border); stroke-width: 1; }
.grid text { font-size: 11px; fill: var(--muted); font-variant-numeric: tabular-nums; }
.line { fill: none; stroke: var(--series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.area { fill: color-mix(in srgb, var(--series-1) 10%, transparent); stroke: none; }
.end, .dot { fill: var(--series-1); stroke: var(--surface); stroke-width: 2; }
.cross { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
.tooltip {
  position: absolute;
  transform: translate(-50%, calc(-100% - 12px));
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.35rem 0.6rem;
  font-size: 0.75rem;
  color: var(--text);
  white-space: nowrap;
  pointer-events: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.tooltip strong { font-size: 0.9rem; color: var(--strong); }
.empty { margin: 2rem 0; text-align: center; }
</style>
