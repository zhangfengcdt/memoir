// Pure helpers: parsing the store's git log, deciding what is "new this turn",
// and rendering the one-line hint and the plain-text fallback. Nothing here
// touches `$`, so every rule is unit-testable without a store.

import type { MemoirCapture, MemoirKeyChange, MemoirMemory, MemoirMemoryAction, MemoirStatus, MemoirTurnMetrics } from '../../types'

export type LogEntry = Omit<MemoirCapture, 'content'>

export type ParsedLog = {
  /** Every commit's sha, newest first. */
  order: string[]
  /** The `Store <key> in <namespace>` commits among them, newest first. */
  entries: LogEntry[]
}

const SUBJECT = /^Store (\S+) in (\S+)$/
const DELETION = /^Delete (\S+) from (\S+)$/

/** Parse `git log --format=%H%x09%ct%x09%s` output: every commit, keyed ones recognised. */
export function parseLog(stdout: string): ParsedLog {
  const order: string[] = []
  const entries: LogEntry[] = []
  for (const line of stdout.split('\n')) {
    const [sha, ct, ...rest] = line.split('\t')
    if (!sha || !ct) continue
    order.push(sha)
    const at = Number(ct)
    if (!Number.isFinite(at)) continue
    const subject = rest.join('\t')
    const stored = SUBJECT.exec(subject)
    const deleted = stored ? null : DELETION.exec(subject)
    const match = stored ?? deleted
    entries.push({
      sha,
      at,
      subject,
      kind: stored ? 'store' : deleted ? 'delete' : 'other',
      key: match ? match[1]! : null,
      namespace: match ? match[2]! : null,
    })
  }
  return { order, entries }
}

/** The keys named by `Store <key> in <namespace>` subjects, default namespace only. */
export function parseStoredKeys(subjects: string): Set<string> {
  const keys = new Set<string>()
  for (const line of subjects.split('\n')) {
    const match = SUBJECT.exec(line.trim())
    if (match && match[2] === 'default') keys.add(match[1]!)
  }
  return keys
}

export const isMetric = (key: string): boolean => key.startsWith('metrics.')

export function visibleCaptures<T extends { key: string | null }>(captures: readonly T[], showMetrics: boolean): T[] {
  return captures.filter(c => showMetrics || c.key === null || !isMetric(c.key))
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

/** Memories stored this turn, metrics excluded: the hint line's `+N`. */
export function newCount(
  captures: readonly { sha: string; kind: string; key: string | null }[],
  order: readonly string[],
  baseline: string | null,
): number {
  const fresh = newShas(order, baseline)
  return captures.filter(c => fresh.has(c.sha) && c.kind === 'store' && c.key !== null && !isMetric(c.key)).length
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
/**
 * The commit count's label: on a branch the count is what sits on top of
 * main, so it reads `+N changes`. While metrics are hidden the count leaves
 * the `metrics.*` writes out, so it matches what the Recent tab lists.
 */
export function commitsLabel(status: MemoirStatus, showMetrics = true): string | null {
  const n = showMetrics ? status.commits : (status.commitsWithoutMetrics ?? status.commits)
  if (n === null) return null
  return status.branch && status.branch !== 'main' ? `+${plural(n, 'change', 'changes')}` : plural(n, 'commit', 'commits')
}

export function statusLine(status: MemoirStatus, showMetrics = true): string {
  const parts: string[] = []
  if (status.branch) parts.push(status.branch)
  if (status.memories !== null) parts.push(plural(status.memories, 'memory', 'memories'))
  const commits = commitsLabel(status, showMetrics)
  if (commits !== null) parts.push(commits)
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

/** The store path for the header: home shown as `~`, cut from the left to fit `max` columns. */
export function storeLabel(path: string, home: string | null, max: number): string {
  const short = home && (path === home || path.startsWith(`${home}/`)) ? `~${path.slice(home.length)}` : path
  if (max < 2) return ''
  return short.length <= max ? short : `…${short.slice(short.length - (max - 1))}`
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
  // The list below leaves metrics writes out, so the count does too.
  const lines = [`memoir: ${statusLine(status, false)}`]
  const shown = visibleCaptures(captures, false).slice(0, limit)
  if (shown.length === 0) {
    lines.push('No captures yet.')
    return lines.join('\n')
  }
  lines.push('Recent commits:')
  for (const c of shown) {
    const content = c.content ? `: ${wrapLines(c.content, 80, 1)[0] ?? ''}` : ''
    lines.push(`  ${relativeTime(nowMs, c.at).padEnd(12)} ${c.subject}${content}`)
  }
  return lines.join('\n')
}

/** `2026-10-11 04:47` in the local time zone. */
export function absoluteTime(atSec: number): string {
  const d = new Date(atSec * 1000)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`
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

/**
 * Compare the branch's keys with main. With `changes` (the CLI's key-level
 * diff, both values known) every difference is exact, and a key main holds
 * that the branch dropped is listed as `removed`. Without it, from git
 * history alone: a key the branch wrote since leaving main is `changed` when
 * main's history ever stored it, else `added`, and main's values stay unknown.
 * With neither, every key is `same`; the caller records that no base was compared.
 */
export function diffMemories(
  keys: readonly string[],
  current: ReadonlyMap<string, string | null>,
  changes: ReadonlyMap<string, MemoirKeyChange> | null,
  history: { written: ReadonlySet<string>; onBase: ReadonlySet<string> } | null,
): MemoirMemory[] {
  const items: MemoirMemory[] = [...keys].sort().map(key => {
    const content = current.get(key) ?? null
    const change = changes?.get(key)
    if (changes) {
      const status: MemoirMemory['status'] = change?.operation === 'added' ? 'added' : change?.operation === 'modified' ? 'changed' : 'same'
      return { key, content, base: change?.old ?? null, status }
    }
    let status: MemoirMemory['status'] = 'same'
    if (history && history.written.has(key)) status = history.onBase.has(key) ? 'changed' : 'added'
    return { key, content, base: null, status }
  })
  if (changes) {
    const present = new Set(keys)
    for (const change of changes.values()) {
      if (change.operation === 'removed' && !present.has(change.key)) {
        items.push({ key: change.key, content: null, base: change.old, status: 'removed' })
      }
    }
    items.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
  }
  return items
}

/** The memories whose key contains `query` (case-insensitive); all of them for a blank query. */
export function filterMemories<T extends { key: string }>(items: readonly T[], query: string): T[] {
  const q = query.trim().toLowerCase()
  return q ? items.filter(m => m.key.toLowerCase().includes(q)) : [...items]
}

/** Wrap each line of `text` (newlines kept) to `width`, at most `max` lines in all. */
export function wrapText(text: string, width: number, max: number): string[] {
  const out: string[] = []
  for (const paragraph of text.split('\n')) {
    if (out.length >= max) break
    if (!paragraph.trim()) {
      out.push('')
      continue
    }
    out.push(...wrapLines(paragraph, width, max - out.length))
  }
  return out.slice(0, max)
}

export const MARKS: Record<MemoirMemory['status'], string> = { added: '+', changed: '~', removed: '-', same: ' ' }

/** The memoir mark in three rows of box drawing: the logo's arch over its two loops. */
export const LOGO: readonly string[] = [' ┏━━━━━┓ ', '┏┛┏┓ ┏┓┗┓', '┗━┛┗━┛┗━┛']

export type MemoryAction = { verb: string; kind: MemoirMemoryAction; hotkey: string }

/**
 * What the detail view can do to a memory: forget it on this branch (any key
 * that is here), and put main's value back (a key main holds, when that
 * value could be read). A `~` key offers both.
 */
export function memoryActions(m: MemoirMemory, base: string | null): MemoryAction[] {
  const actions: MemoryAction[] = []
  if (m.status !== 'removed') actions.push({ verb: 'forget key', kind: 'forget', hotkey: 'd' })
  if ((m.status === 'changed' || m.status === 'removed') && m.base !== null) {
    actions.push({
      verb: m.status === 'changed' ? `restore ${base ?? 'main'}'s value` : `restore from ${base ?? 'main'}`,
      kind: 'restore',
      hotkey: 'u',
    })
  }
  return actions
}

/** Another branch's differences from main, from the CLI's key-level diff: both values known. */
export function itemsFromChanges(changes: Iterable<MemoirKeyChange>): MemoirMemory[] {
  const items: MemoirMemory[] = []
  for (const c of changes) {
    const status: MemoirMemory['status'] = c.operation === 'added' ? 'added' : c.operation === 'removed' ? 'removed' : 'changed'
    items.push({ key: c.key, content: c.new, base: c.old, status })
  }
  return items.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
}

/** Another branch's differences from main, from git history alone: which keys it wrote, no values. */
export function itemsFromHistory(history: { written: ReadonlySet<string>; onBase: ReadonlySet<string> }): MemoirMemory[] {
  return [...history.written]
    .sort()
    .map(key => ({ key, content: null, base: null, status: history.onBase.has(key) ? 'changed' : 'added' }))
}
