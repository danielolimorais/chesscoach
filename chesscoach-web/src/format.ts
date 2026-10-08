// Formatação e rótulos em português do Brasil.
import type { Phase, Result, Severity } from './api'

const nf1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })

export function num(value: number | null | undefined, digits: 0 | 1 = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return digits === 1 ? nf1.format(value) : nf0.format(value)
}

export function pct(value: number | null | undefined, digits: 0 | 1 = 0): string {
  return value === null || value === undefined ? '–' : `${num(value, digits)}%`
}

export function formatDate(value?: string | null): string {
  if (!value) return '–'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '–' : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
}

export function formatDateLong(value?: string | null): string {
  if (!value) return '–'
  const d = new Date(value)
  return Number.isNaN(d.getTime())
    ? '–'
    : d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatClock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return ''
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const colorLabel = (c: string) => (c.toLowerCase() === 'white' ? 'Brancas' : 'Pretas')

export const resultLabel: Record<Result, string> = { win: 'Vitória', loss: 'Derrota', draw: 'Empate' }
export const resultShort: Record<Result, string> = { win: 'V', loss: 'D', draw: 'E' }

export const severityLabel: Record<Severity, string> = {
  best: 'Melhor lance',
  good: 'Bom lance',
  inaccuracy: 'Imprecisão',
  mistake: 'Erro',
  blunder: 'Blunder',
}

export const phaseLabel: Record<Phase, string> = {
  opening: 'Abertura',
  middlegame: 'Meio-jogo',
  endgame: 'Final',
}

export function timeClassLabel(tc?: string | null): string {
  const labels: Record<string, string> = {
    bullet: 'Bullet',
    blitz: 'Blitz',
    rapid: 'Rápida',
    classical: 'Clássica',
    daily: 'Diária',
  }
  return tc ? labels[tc] ?? tc : '–'
}

export const isError = (s: Severity) => s === 'inaccuracy' || s === 'mistake' || s === 'blunder'

export function uciToSquares(uci: string | null | undefined): [string, string] | null {
  return uci && uci.length >= 4 ? [uci.slice(0, 2), uci.slice(2, 4)] : null
}
