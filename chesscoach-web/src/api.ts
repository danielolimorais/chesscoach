// Cliente da API do ChessCoach (backend FastAPI em api.py).
// Para trocar o endereço sem mexer no código: crie .env com VITE_API_URL=http://localhost:8000

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Color = 'white' | 'black'
export type Result = 'win' | 'loss' | 'draw'
export type Severity = 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder'
export type Phase = 'opening' | 'middlegame' | 'endgame'
export type TimeClass = 'bullet' | 'blitz' | 'rapid' | 'classical' | 'daily'

export interface RatingInfo {
  rating: number | null
  best: number | null
  wins: number
  losses: number
  draws: number
}

export interface Profile {
  username: string
  name?: string | null
  title?: string | null
  avatar?: string | null
  url?: string
  ratings: Partial<Record<'rapid' | 'blitz' | 'bullet', RatingInfo>>
}

export interface Job {
  status: 'idle' | 'running' | 'done' | 'error'
  done: number
  total: number
  failed?: number
  error?: string | null
}

export interface SyncResult {
  imported: number
  found: number
  total: number
  job: Job
}

export interface GameSummary {
  id: string
  played_at: string | null
  color: Color
  result: Result
  opp_name: string | null
  opp_rating: number | null
  my_rating: number | null
  time_class: TimeClass | null
  opening_name: string | null
  accuracy: number | null
  blunders: number | null
  mistakes: number | null
  analyzed: number | boolean
}

export interface ResultStats {
  games: number
  wins: number
  draws: number
  losses: number
  score_pct: number
}

export interface PhaseStats {
  phase: Phase
  moves: number
  acpl: number | null
  accuracy: number | null
  blunders: number
  mistakes: number
  inaccuracies: number
  error_rate: number
}

export interface ErrorType {
  key: string
  label: string
  count: number
  share: number
}

export interface TopMistake {
  game_id: string
  ply: number
  move_number: number
  color: Color
  fen_before: string
  played_move: string
  played_uci: string
  best_move: string | null
  best_uci: string | null
  win_drop: number
  cp_loss: number
  severity: Severity
  phase: Phase
  time_pressure: boolean
  category: string
  category_label: string
  opp_name: string | null
  played_at: string | null
}

export interface OpeningStats extends ResultStats {
  name: string
  color: Color
  accuracy: number | null
}

export interface Report {
  username: string
  generated_at: string
  limit: number
  total_games: number
  analyzed_games: number
  complete: boolean
  results: {
    overall: ResultStats
    white: ResultStats
    black: ResultStats
    by_time_class: Record<string, ResultStats>
  }
  quality: {
    accuracy: number | null
    acpl: number | null
    accuracy_white: number | null
    accuracy_black: number | null
    acpl_white: number | null
    acpl_black: number | null
    blunders_per_game: number | null
    mistakes_per_game: number | null
    blunders: number
    mistakes: number
    inaccuracies: number
  }
  phases: PhaseStats[]
  error_types: ErrorType[]
  time_pressure: {
    moves: number
    share_of_moves: number
    error_rate_pressure: number
    error_rate_normal: number
    share_of_serious_errors: number
  }
  openings: OpeningStats[]
  advantage: { wasted: number; saved: number; wasted_games: string[] }
  rating: { time_class: string | null; history: { date: string; rating: number }[] }
  top_mistakes: TopMistake[]
  insights: string[]
  games: GameSummary[]
}

export interface MoveAnalysis {
  ply: number
  move_number: number
  color: Color
  is_user: boolean
  played_move: string
  played_uci: string
  best_move: string | null
  best_uci: string | null
  fen_before: string
  eval_before: number | null
  eval_after: number | null
  eval_text: string
  cp_loss: number
  win_drop: number
  accuracy: number
  severity: Severity
  phase: Phase
  clock_seconds: number | null
  time_pressure: boolean
}

export interface GameAnalysis {
  game: {
    id: string
    color: Color
    result: Result
    played_at: string | null
    opp_name: string | null
    opp_rating: number | null
    my_rating: number | null
    time_control: string | null
    time_class: TimeClass | null
    opening_name: string | null
    url: string | null
    termination: string | null
  }
  summary: {
    accuracy: number | null
    acpl: number | null
    blunders: number
    mistakes: number
    inaccuracies: number
    user_moves: number
  }
  moves: MoveAnalysis[]
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 30_000): Promise<T> {
  // Sem limite de tempo, um backend travado deixaria a tela "carregando" para sempre.
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal })
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      throw new Error(
        `A API não respondeu em ${Math.round(timeoutMs / 1000)} s. Veja o terminal do backend ` +
          '(uvicorn): se houver erro, pare com Ctrl+C e rode "uvicorn api:app --reload" de novo.',
      )
    }
    throw new Error(`Não consegui conectar à API em ${API_URL}. O backend está rodando?`)
  } finally {
    window.clearTimeout(timer)
  }
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(detail || `A API respondeu com erro ${res.status}.`)
  }
  return res.json() as Promise<T>
}

const u = (name: string) => encodeURIComponent(name.trim())

export const api = {
  profile: (nick: string) => request<Profile>(`/api/player/${u(nick)}/profile`),
  sync: (nick: string, limit = 30) =>
    request<SyncResult>(`/api/player/${u(nick)}/sync?limit=${limit}`, { method: 'POST' }, 120_000),
  job: (nick: string) => request<Job>(`/api/player/${u(nick)}/job`),
  report: (nick: string, limit = 30) => request<Report>(`/api/player/${u(nick)}/report?limit=${limit}`),
  game: (id: string) => request<GameAnalysis>(`/api/game/${encodeURIComponent(id)}/analysis`, {}, 180_000),
}
