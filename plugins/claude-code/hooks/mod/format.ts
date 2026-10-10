// Pure helpers: parsing the store's git log, deciding what is "new this turn",
// and rendering the one-line hint and the plain-text fallback. Nothing here
// touches `$`, so every rule is unit-testable without a store.

import type { MemoirCapture, MemoirStatus, MemoirTurnMetrics } from '../../types'

export type LogEntry = Omit<MemoirCapture, 'content'>

export type ParsedLog = {
  /** Every commit's sha, newest first. */
  order: string[]
  /** The `Store <key> in <namespace>` commits among them, newest first. */
  entries: LogEntry[]
}

const SUBJECT = /^Store (\S+) in (\S+)$/

/** Parse `git log --format=%H%x09%ct%x09%s` output. */
export function parseLog(stdout: string): ParsedLog {
  const order: string[] = []
  const entries: LogEntry[] = []
  for (const line of stdout.split('\n')) {
    const [sha, ct, ...rest] = line.split('\t')
    if (!sha || !ct) continue
    order.push(sha)
    const at = Number(ct)
    const match = SUBJECT.exec(rest.join('\t'))
    if (!match || !Number.isFinite(at)) continue
    entries.push({ sha, at, key: match[1]!, namespace: match[2]! })
  }
  return { order, entries }
}

export const isMetric = (key: string): boolean => key.startsWith('metrics.')

export function visibleCaptures<T extends { key: string }>(captures: readonly T[], showMetrics: boolean): T[] {
  return captures.filter(c => showMetrics || !isMetric(c.key))
}

/**
 * Shas committed after `baseline` (the head when the turn started): everything
 * in `order` ahead of it. A baseline that fell out of the window means every
 * commit in it is newer; no baseline means nothing is new yet.
 */
export function newShas(order: readonly string[], baseline: string | null): Set<string> {
  if (baseline === null) return new Set()
  const i = order.indexOf(baseline)
  return new Set(order.slice(0, i === -1 ? order.length : i))
}

/** Captures that landed this turn, metrics excluded: the hint line's `+N`. */
export function newCount(
  captures: readonly { sha: string; key: string }[],
  order: readonly string[],
  baseline: string | null,
): number {
  const fresh = newShas(order, baseline)
  return captures.filter(c => fresh.has(c.sha) && !isMetric(c.key)).length
}

/** Read `.git/HEAD`: a branch name, or the short sha of a detached head. */
export function parseHead(text: string): { branch: string | null; ref: string | null } {
  const line = text.split('\n')[0]?.trim() ?? ''
  if (line.startsWith('ref: ')) {
    const ref = line.slice('ref: '.length)
    return { branch: ref.replace(/^refs\/heads\//, ''), ref }
  }
  if (line) return { branch: line.slice(0, 8), ref: null }
  return { branch: null, ref: null }
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** `main · 18 memories · 61 commits`, dropping what is unknown. */
export function statusLine(status: MemoirStatus): string {
  const parts: string[] = []
  if (status.branch) parts.push(status.branch)
  if (status.memories !== null) parts.push(plural(status.memories, 'memory', 'memories'))
  if (status.commits !== null) parts.push(plural(status.commits, 'commit', 'commits'))
  return parts.join(' · ')
}

/** The hint-line suffix, or undefined when there is nothing to show. */
export function hintTail(status: MemoirStatus, fresh: number): string | undefined {
  if (!status.store || !status.branch) return undefined
  const parts = [`memoir: ${status.branch}`]
  if (status.memories !== null) parts.push(plural(status.memories, 'memory', 'memories'))
  if (fresh > 0) parts.push(`+${fresh} this turn`)
  return parts.join(' · ')
}

/** True when the person's settings already route memoir into the status line. */
export function usesStatuslineScript(settings: Readonly<Record<string, unknown>>): boolean {
  const statusLineSetting = settings['statusLine']
  if (!statusLineSetting || typeof statusLineSetting !== 'object') return false
  const command = (statusLineSetting as Record<string, unknown>)['command']
  return typeof command === 'string' && command.includes('statusline.sh')
}

export function relativeTime(nowMs: number, atSec: number): string {
  const s = Math.max(0, Math.floor(nowMs / 1000) - atSec)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} ${h === 1 ? 'hour' : 'hours'} ago`
  const d = Math.floor(h / 24)
  return `${d} ${d === 1 ? 'day' : 'days'} ago`
}

/** Greedy word wrap into at most `max` lines of `width` cells, the last one elided. */
export function wrapLines(text: string, width: number, max: number): string[] {
  const w = Math.max(4, width)
  const words = text.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean)
  const chunks: string[] = []
  let current = ''
  for (const word of words) {
    if (!current) current = word
    else if (current.length + 1 + word.length <= w) current += ' ' + word
    else {
      chunks.push(current)
      current = word
    }
  }
  if (current) chunks.push(current)
  const cut = chunks.flatMap(c => {
    const out: string[] = []
    for (let i = 0; i < c.length; i += w) out.push(c.slice(i, i + w))
    return out
  })
  if (cut.length <= max) return cut
  const kept = cut.slice(0, max)
  const last = kept[max - 1]!
  kept[max - 1] = (last.length >= w ? last.slice(0, w - 1) : last) + '…'
  return kept
}

export type TaxonomyGroup = {
  name: string
  count: number
  leaves: { path: string; count: number }[]
}

/** Group leaf paths by their first segment, each group's leaves sorted. */
export function groupTaxonomy(prefixCounts: Readonly<Record<string, number>>, showMetrics: boolean): TaxonomyGroup[] {
  const groups = new Map<string, TaxonomyGroup>()
  for (const [path, count] of Object.entries(prefixCounts)) {
    if (!showMetrics && isMetric(path)) continue
    const dot = path.indexOf('.')
    const name = dot === -1 ? path : path.slice(0, dot)
    const leaf = dot === -1 ? '' : path.slice(dot + 1)
    const group = groups.get(name) ?? { name, count: 0, leaves: [] }
    group.count += count
    if (leaf) group.leaves.push({ path: leaf, count })
    groups.set(name, group)
  }
  return [...groups.values()]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(g => ({ ...g, leaves: [...g.leaves].sort((a, b) => a.path.localeCompare(b.path)) }))
}

/** What `/memoir:pane` prints where nothing can draw a pane. */
export function textSummary(
  status: MemoirStatus,
  captures: readonly MemoirCapture[],
  nowMs: number,
  limit = 10,
): string {
  if (!status.store) return 'No memoir store for this folder.'
  const lines = [`memoir: ${statusLine(status)}`]
  const shown = visibleCaptures(captures, false).slice(0, limit)
  if (shown.length === 0) {
    lines.push('No captures yet.')
    return lines.join('\n')
  }
  lines.push('Recent captures:')
  for (const c of shown) {
    const content = c.content ? `: ${wrapLines(c.content, 80, 1)[0] ?? ''}` : ''
    lines.push(`  ${relativeTime(nowMs, c.at).padEnd(12)} ${c.key}${content}`)
  }
  return lines.join('\n')
}

export const TURN_METRICS_PREFIX = 'metrics.turn.'

/** Parse a `metrics.turn.<branch>` value as the Stop hook's merge-metrics.py writes it. */
export function parseTurnMetrics(content: string | null | undefined): MemoirTurnMetrics | null {
  if (!content) return null
  let raw: unknown
  try {
    raw = JSON.parse(content)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object') return null
  const v = raw as Record<string, unknown>
  const num = (key: string) => (typeof v[key] === 'number' && Number.isFinite(v[key]) ? (v[key] as number) : 0)
  return {
    turns: num('turns_count'),
    toolCalls: num('total_tool_calls'),
    toolErrors: num('total_tool_errors'),
    repeatedToolCalls: num('total_repeated_tool_calls'),
    outputChars: num('total_output_chars'),
    toolInputChars: num('total_tool_input_chars'),
    toolResultChars: num('total_tool_result_chars'),
    latencyMs: num('total_latency_ms'),
    latencySamples: num('latency_samples'),
  }
}

/** `28285` → `28k`, `1470251` → `1.5M`; small numbers stay as they are. */
export function compactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${Math.round(n / 1_000)}k`
  return String(Math.round(n))
}

export type MetricChart = {
  title: string
  rows: { branch: string; isCurrent: boolean; value: number; label: string }[]
}

const METRICS: { title: string; pick: (m: MemoirTurnMetrics) => number | null; format: (n: number) => string }[] = [
  { title: 'Turns', pick: m => m.turns, format: compactNumber },
  { title: 'Tool calls', pick: m => m.toolCalls, format: compactNumber },
  { title: 'Tool errors', pick: m => m.toolErrors, format: compactNumber },
  { title: 'Avg latency (s)', pick: m => (m.latencySamples > 0 ? m.latencyMs / m.latencySamples / 1000 : null), format: n => n.toFixed(1) },
  { title: 'Output chars', pick: m => m.outputChars, format: compactNumber },
  { title: 'Tool result chars', pick: m => m.toolResultChars, format: compactNumber },
]

/**
 * One chart per metric, branches as rows in one fixed order (the current
 * branch first, then by name) so a row keeps its place from chart to chart.
 * A branch with no sample for a metric is left out of that chart.
 */
export function metricCharts(metrics: Readonly<Record<string, MemoirTurnMetrics>>, current: string | null): MetricChart[] {
  const branches = Object.keys(metrics).sort((a, b) => {
    if (a === current) return -1
    if (b === current) return 1
    return a.localeCompare(b)
  })
  return METRICS.map(metric => ({
    title: metric.title,
    rows: branches.flatMap(branch => {
      const value = metric.pick(metrics[branch]!)
      return value === null ? [] : [{ branch, isCurrent: branch === current, value, label: metric.format(value) }]
    }),
  }))
}

/** A bar of `width` cells at most, scaled to `max`; anything above zero shows at least one cell. */
export function bar(value: number, max: number, width: number): string {
  if (value <= 0 || max <= 0 || width <= 0) return ''
  return '█'.repeat(Math.max(1, Math.round((value / max) * width)))
}
