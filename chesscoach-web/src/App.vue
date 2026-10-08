<template>
  <SearchScreen
    v-if="screen === 'search'"
    :loading="searching"
    :step="searchStep"
    :error="searchError"
    :initial-nick="nick"
    :limit="limit"
    @submit="startSession"
  />

  <div v-else class="app">
    <header class="topbar">
      <button class="brand" type="button" title="Voltar ao relatório" @click="openReport">
        <span aria-hidden="true">♞</span> ChessCoach
      </button>

      <div class="player">
        <img v-if="profile?.avatar" class="avatar" :src="profile.avatar" alt="" />
        <span v-else class="avatar initial" aria-hidden="true">{{ displayName.charAt(0).toUpperCase() }}</span>
        <div class="player-text">
          <a v-if="profile?.url" class="player-name" :href="profile.url" target="_blank" rel="noopener">
            <span v-if="profile.title" class="title-badge">{{ profile.title }}</span>{{ displayName }}
          </a>
          <span v-else class="player-name">{{ displayName }}</span>
          <span class="ratings">
            <span v-for="r in ratings" :key="r.key" :title="`Melhor: ${r.best ?? '–'}`">
              {{ r.label }} <b>{{ r.rating }}</b>
            </span>
          </span>
        </div>
      </div>

      <div class="top-actions">
        <button class="btn ghost" type="button" @click="changePlayer">Trocar jogador</button>
      </div>
    </header>

    <div :class="['body', { 'with-sidebar': showSidebar }]">
      <div v-if="showSidebar" class="sidebar">
        <GameList
          :games="report?.games ?? []"
          :selected-id="view.kind === 'game' ? view.id : null"
          @select="openGame"
        />
      </div>

      <main class="main">
        <GeneratePanel
          v-if="generating || gen.stage === 'error' || !report"
          v-model:limit="limit"
          :nick="displayName"
          :stage="gen.stage"
          :failed-at="gen.failedAt"
          :found="gen.found"
          :imported="gen.imported"
          :done="gen.done"
          :total="gen.total"
          :error="gen.error"
          @generate="generate"
          @cancel="gen.stage = 'idle'"
        />
        <GameViewer
          v-else-if="view.kind === 'game'"
          :game-id="view.id"
          :initial-ply="view.ply"
          @back="openReport"
        />
        <ReportView
          v-else
          v-model:limit="limit"
          :report="report"
          @open-game="openGame"
          @regenerate="generate"
        />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, type Profile, type Report } from './api'
import GameList from './components/GameList.vue'
import GameViewer from './components/GameViewer.vue'
import GeneratePanel, { type Stage } from './components/GeneratePanel.vue'
import ReportView from './components/ReportView.vue'
import SearchScreen from './components/SearchScreen.vue'

const POLL_MS = 1500
const NICK_KEY = 'chesscoach:last-nick'

type View = { kind: 'report' } | { kind: 'game'; id: string; ply: number | null }

const screen = ref<'search' | 'dashboard'>('search')
const nick = ref(readSavedNick())
const limit = ref(30)
const profile = ref<Profile | null>(null)
const report = ref<Report | null>(null)
const view = ref<View>({ kind: 'report' })

const searching = ref(false)
const searchStep = ref('')
const searchError = ref('')

const gen = reactive({
  stage: 'idle' as Stage,
  failedAt: null as Stage | null,
  found: 0,
  imported: 0,
  done: 0,
  total: 0,
  error: '',
})
let genToken = 0 // invalida uma geração em andamento (ex.: ao trocar de jogador)

const generating = computed(() => ['download', 'analyze', 'build'].includes(gen.stage))
const showSidebar = computed(() => !!report.value && !generating.value && gen.stage !== 'error')

function readSavedNick(): string {
  try {
    return localStorage.getItem(NICK_KEY) ?? ''
  } catch {
    return ''
  }
}
function saveNick(value: string) {
  try {
    localStorage.setItem(NICK_KEY, value)
  } catch {
    /* armazenamento indisponível: tudo bem */
  }
}

const displayName = computed(() => profile.value?.username || nick.value)
const ratings = computed(() => {
  const r = profile.value?.ratings ?? {}
  return (
    [
      ['bullet', 'Bullet'],
      ['blitz', 'Blitz'],
      ['rapid', 'Rápida'],
    ] as const
  )
    .filter(([key]) => r[key]?.rating)
    .map(([key, label]) => ({ key, label, rating: r[key]!.rating, best: r[key]!.best }))
})

/** Busca o perfil e, se já existir um relatório completo no banco, mostra direto. */
async function startSession(value: string) {
  searching.value = true
  searchError.value = ''
  nick.value = value
  try {
    searchStep.value = 'Buscando o perfil no Chess.com…'
    profile.value = await api.profile(value)
    saveNick(value)
    report.value = null
    try {
      const existing = await api.report(value, limit.value)
      if (existing.complete) report.value = existing
    } catch {
      /* ainda não há partidas desse jogador no banco */
    }
    Object.assign(gen, { stage: 'idle', failedAt: null, error: '' })
    view.value = { kind: 'report' }
    screen.value = 'dashboard'
  } catch (e) {
    searchError.value = (e as Error).message
  } finally {
    searching.value = false
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** Baixa as partidas, espera a análise terminar e só então mostra o relatório. */
async function generate() {
  const token = ++genToken
  const alive = () => token === genToken
  Object.assign(gen, { stage: 'download', failedAt: null, error: '', found: 0, imported: 0, done: 0, total: 0 })
  view.value = { kind: 'report' }
  try {
    const sync = await api.sync(nick.value, limit.value)
    if (!alive()) return
    Object.assign(gen, {
      stage: 'analyze',
      found: sync.found,
      imported: sync.imported,
      total: sync.total,
      done: sync.job.done,
    })

    for (;;) {
      const job = await api.job(nick.value)
      if (!alive()) return
      gen.done = job.done
      gen.total = job.total || gen.total
      if (job.status === 'error') throw new Error(job.error || 'A análise falhou.')
      if (job.status !== 'running') break
      await sleep(POLL_MS)
    }

    gen.stage = 'build'
    const fresh = await api.report(nick.value, limit.value)
    if (!alive()) return
    report.value = fresh
    gen.stage = 'done'
  } catch (e) {
    if (!alive()) return
    gen.failedAt = gen.stage
    gen.stage = 'error'
    gen.error = (e as Error).message
  }
}

function openGame(id: string, ply?: number) {
  view.value = { kind: 'game', id, ply: ply ?? null }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openReport() {
  view.value = { kind: 'report' }
}

function changePlayer() {
  genToken++
  profile.value = null
  report.value = null
  Object.assign(gen, { stage: 'idle', failedAt: null, error: '' })
  view.value = { kind: 'report' }
  screen.value = 'search'
}
</script>

<style scoped>
.app {
  --topbar-h: 64px;
  min-height: 100vh;
}

/* ---------- barra superior ---------- */
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 1.75rem;
  height: var(--topbar-h);
  padding: 0 1.5rem;
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0;
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--strong);
  background: none;
  border: 0;
  cursor: pointer;
}
.brand span { font-size: 1.3rem; }

.player { display: flex; align-items: center; gap: 0.7rem; min-width: 0; padding-left: 1.75rem; border-left: 1px solid var(--border); }
.avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  object-fit: cover;
  background: var(--surface-2);
}
.avatar.initial { display: grid; place-items: center; font-weight: 700; color: var(--primary); background: var(--primary-soft); }
.player-text { display: flex; flex-direction: column; min-width: 0; }
.player-name {
  overflow: hidden;
  font-weight: 700;
  color: var(--strong);
  text-decoration: none;
  white-space: nowrap;
  text-overflow: ellipsis;
}
a.player-name:hover { text-decoration: underline; }
.title-badge {
  margin-right: 0.35rem;
  padding: 0 0.3rem;
  font-size: 0.75rem;
  color: #fff;
  background: #b33430;
  border-radius: 4px;
}
.ratings { display: flex; gap: 0.75rem; font-size: 0.78rem; color: var(--muted); white-space: nowrap; }
.ratings b { color: var(--strong); font-variant-numeric: tabular-nums; }

.top-actions { display: flex; gap: 0.5rem; margin-left: auto; }
.top-actions .btn { padding: 0.5rem 0.95rem; font-size: 0.86rem; }

/* ---------- corpo: ocupa a tela inteira ---------- */
.body { display: grid; grid-template-columns: minmax(0, 1fr); }
.body.with-sidebar { grid-template-columns: 290px minmax(0, 1fr); }

.sidebar {
  position: sticky;
  top: var(--topbar-h);
  height: calc(100vh - var(--topbar-h));
  padding: 1.1rem 0.75rem 1rem 1rem;
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.main { min-width: 0; padding: 1.75rem 2rem 3rem; }

@media (max-width: 900px) {
  .topbar { position: static; flex-wrap: wrap; height: auto; gap: 0.75rem 1rem; padding: 0.75rem 1rem; }
  .player { padding-left: 1rem; }
  .top-actions { margin-left: 0; width: 100%; }
  .top-actions .btn { flex: 1; }
  .body.with-sidebar { grid-template-columns: minmax(0, 1fr); }
  .sidebar { position: static; height: 320px; border-right: 0; border-bottom: 1px solid var(--border); }
  .main { padding: 1rem; }
}
</style>
