<template>
  <!-- O chessground assume esta div. Ela ocupa 100% da largura do pai e é sempre quadrada. -->
  <div ref="boardRef" class="board" :class="{ small }"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chessground } from 'chessground'
import type { Api } from 'chessground/api'
import type { Config } from 'chessground/config'
import type { DrawShape } from 'chessground/draw'
import type { Key } from 'chessground/types'

import 'chessground/assets/chessground.base.css'
import 'chessground/assets/chessground.brown.css'
import 'chessground/assets/chessground.cburnett.css'

export interface Arrow {
  from: string
  to: string
  brush: 'green' | 'red' | 'blue' | 'yellow'
}

const props = withDefaults(
  defineProps<{
    fen: string
    orientation?: 'white' | 'black'
    lastMove?: [string, string] | null
    arrows?: Arrow[]
    coordinates?: boolean
    small?: boolean // tabuleiros em miniatura (sem coordenadas, setas mais finas)
  }>(),
  { orientation: 'white', lastMove: null, arrows: () => [], coordinates: true, small: false },
)

const boardRef = ref<HTMLElement | null>(null)
let cg: Api | null = null

function config(): Config {
  const shapes: DrawShape[] = props.arrows.map((a) => ({
    orig: a.from as Key,
    dest: a.to as Key,
    brush: a.brush,
  }))
  return {
    fen: props.fen,
    orientation: props.orientation,
    viewOnly: true,
    coordinates: props.coordinates && !props.small,
    lastMove: props.lastMove ? (props.lastMove as Key[]) : undefined,
    animation: { enabled: true, duration: 160 },
    drawable: { enabled: false, visible: true, autoShapes: shapes },
  }
}

onMounted(() => {
  if (boardRef.value) cg = Chessground(boardRef.value, config())
})

watch(
  () => [props.fen, props.orientation, props.lastMove, props.arrows, props.coordinates],
  () => {
    if (!cg) return
    // "lastMove: undefined" não apaga o destaque anterior; por isso limpamos à mão.
    if (!props.lastMove) cg.state.lastMove = undefined
    cg.set(config())
  },
  { deep: true },
)

onBeforeUnmount(() => cg?.destroy())
</script>

<style scoped>
.board {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 6px;
}
</style>

<style>
/* Ajustes globais do chessground: coordenadas dentro das casas, legíveis em qualquer tamanho. */
.cg-wrap coords {
  font-family: var(--font);
  font-weight: 600;
  font-size: clamp(9px, 1.4vmin, 12px);
}
.cg-wrap coords.ranks {
  left: 3px;
  top: 2px;
  height: 100%;
  width: 12px;
  align-items: flex-start;
}
.cg-wrap coords.files {
  bottom: 1px;
  left: 0;
  width: 100%;
  text-align: right;
}
.cg-wrap coords.files coord {
  padding-right: 4px;
}
</style>
