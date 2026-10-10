// Tests for the memoir mod. The kit gives the engine's `$` with the plugin
// loaded; these tests sit beneath it and answer the host (git, the CLI, the
// filesystem, settings) from memory, so no store, no memoir and no LLM run.

import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import * as fmt from './format'

const STORE = '/home/u/.memoir/-proj'
const sha = (n: number) => String(n).padStart(40, '0')
const line = (n: number, at: number, subject: string) => `${sha(n)}\t${at}\t${subject}`

const BASE_LOG =
  [
    line(3, 1700000300, 'Store metrics.turn.main in default'),
    line(2, 1700000200, 'Store workflow.coding.gates in default'),
    line(1, 1700000100, 'Store knowledge.decisions.architecture in default'),
    line(0, 1700000000, 'Initialize memoir store'),
  ].join('\n') + '\n'

const CONTENT: Record<string, string> = {
  'workflow.coding.gates': 'Run make format, make lint, make test before every commit',
  'knowledge.decisions.architecture': 'Keep business logic in services/; CLI and MCP stay thin',
  'metrics.turn.main': JSON.stringify({
    schema_version: 1,
    turns_count: 22,
    total_output_chars: 28285,
    total_tool_input_chars: 68100,
    total_tool_result_chars: 146441,
    total_tool_calls: 125,
    total_tool_errors: 0,
    total_repeated_tool_calls: 0,
    total_latency_ms: 1470251,
    latency_samples: 22,
  }),
  'metrics.turn.feat/x': JSON.stringify({
    schema_version: 1,
    turns_count: 5,
    total_output_chars: 5697,
    total_tool_input_chars: 117716,
    total_tool_result_chars: 286132,
    total_tool_calls: 95,
    total_tool_errors: 2,
    total_repeated_tool_calls: 0,
    total_latency_ms: 1562060,
    latency_samples: 5,
  }),
  'preferences.tools.git': 'Prefer rebase over merge for feature branches',
}

const SUMMARY_JSON = JSON.stringify({
  prefix_counts: {
    default: {
      'workflow.coding.gates': 1,
      'knowledge.decisions.architecture': 1,
      'knowledge.technical.build': 2,
      'metrics.turn.main': 1,
      'metrics.turn.feat/x': 1,
    },
  },
})

type World = {
  store: string | null
  exists: boolean
  log: string
  count: string
  cache: string
  head: string
  settings: Record<string, unknown>
  surfaces: string[]
  mtime: number
  placed: boolean
  cliFails: boolean
  runs: string[][]
}

function world(on: On, overrides: Partial<World> = {}) {
  const w: World = {
    store: STORE,
    exists: true,
    log: BASE_LOG,
    count: '61\n',
    cache: '18\n',
    head: 'ref: refs/heads/main\n',
    settings: {},
    surfaces: ['terminal'],
    mtime: 1000,
    placed: true,
    cliFails: false,
    runs: [],
    ...overrides,
  }
  const clock = mock.clock(on, { now: 1700000400_000 })
  mock.env(on, {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('settings.read', () => ({ value: w.settings }))
  on('session.surfaces', () => ({ value: w.surfaces as never }))
  on('ui.open', () => ({ value: (w.placed ? { isPlaced: true } : { isPlaced: false, reason: 'narrow' }) as never }))
  on('fs.exists', () => ({ value: w.exists }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: w.mtime, isLink: false } }))
  on('fs.read', ($, e) => ({
    value: e.path.endsWith('/HEAD') ? w.head : e.path.endsWith('plugin-statusline-cache') ? w.cache : '',
  }))
  on('process.run', ($, e) => {
    w.runs.push([...e.argv])
    const argv = e.argv.join(' ')
    let stdout = ''
    let exitCode = 0
    if (argv.includes('derive-store-path.sh')) {
      stdout = w.store ?? ''
      exitCode = w.store === null ? 1 : 0
    } else if (argv.includes(' log ')) stdout = w.log
    else if (argv.includes('rev-list')) stdout = w.count
    else if (argv.includes(' get ') && w.cliFails) exitCode = 1
    else if (argv.includes(' get ')) {
      const keys = e.argv.slice(e.argv.indexOf('get') + 3)
      stdout = JSON.stringify({
        items: keys.map(key => ({ key, found: key in CONTENT, value: { content: CONTENT[key] } })),
      })
    } else if (argv.includes(' summarize ')) stdout = SUMMARY_JSON
    return { value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { w, clock }
}

async function boot($: Engine, on: On, overrides: Partial<World> = {}) {
  const ctx = world(on, overrides)
  await $.session.start({ cwd: '/proj', surface: 'terminal', isInteractive: true })
  await ctx.clock.settle()
  return ctx
}

const HINT = {
  plugin: 'memoir',
  surface: 'terminal',
  component: 'PromptHint',
  props: { isDraft: false, isWorking: false, hint: '? for shortcuts' },
} as const

const PANE = {
  plugin: 'memoir',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'memoir',
  props: {
    title: 'memoir',
    isFocused: true,
    bodyColumns: 78,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 24 },
    view: {},
  },
} as const

/** The engine's own PromptHint drawing, reduced to the tail the mod added. */
function drawHint(on: On) {
  on('ui.render', { component: 'PromptHint' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{e.props.tail ?? '(no tail)'}</Text>
  })
}

const runCommand = ($: Engine) =>
  $.command.run({
    command: 'memoir:pane',
    args: '',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 120 },
  } as never)

// --- pure rules -------------------------------------------------------------

test('parseLog keeps every sha in order and only Store subjects as captures', () => {
  const parsed = fmt.parseLog(BASE_LOG)
  expect(parsed.order).toEqual([sha(3), sha(2), sha(1), sha(0)])
  expect(parsed.entries.map(c => c.key)).toEqual([
    'metrics.turn.main',
    'workflow.coding.gates',
    'knowledge.decisions.architecture',
  ])
  expect(parsed.entries[1]).toEqual({ sha: sha(2), at: 1700000200, key: 'workflow.coding.gates', namespace: 'default' })
})

test('metrics.* captures are hidden unless asked for', () => {
  const { entries } = fmt.parseLog(BASE_LOG)
  expect(fmt.visibleCaptures(entries, false).map(c => c.key)).toEqual([
    'workflow.coding.gates',
    'knowledge.decisions.architecture',
  ])
  expect(fmt.visibleCaptures(entries, true)).toHaveLength(3)
})

test('newCount counts non-metric captures ahead of the turn baseline', () => {
  const { order, entries } = fmt.parseLog(BASE_LOG)
  expect(fmt.newCount(entries, order, null)).toBe(0)
  expect(fmt.newCount(entries, order, sha(3))).toBe(0)
  expect(fmt.newCount(entries, order, sha(1))).toBe(1) // sha(2) is new, sha(3) is a metric
  expect(fmt.newCount(entries, order, sha(0))).toBe(2)
  expect(fmt.newCount(entries, order, 'gone-from-window')).toBe(2)
})

test('hintTail and textSummary', () => {
  const status = { store: STORE, branch: 'main', head: sha(3), memories: 18, commits: 61 }
  expect(fmt.hintTail(status, 0)).toBe('memoir: main · 18 memories')
  expect(fmt.hintTail(status, 2)).toBe('memoir: main · 18 memories · +2 this turn')
  expect(fmt.hintTail({ ...status, memories: 1 }, 0)).toBe('memoir: main · 1 memory')
  expect(fmt.hintTail({ ...status, store: null }, 0)).toBeUndefined()
  expect(fmt.textSummary({ ...status, store: null }, [], 0)).toBe('No memoir store for this folder.')
  expect(fmt.usesStatuslineScript({ statusLine: { type: 'command', command: 'x | bash ~/p/scripts/statusline.sh' } })).toBe(true)
  expect(fmt.usesStatuslineScript({ statusLine: { type: 'command', command: 'starship' } })).toBe(false)
  expect(fmt.usesStatuslineScript({})).toBe(false)
})

// --- the mod in a session ---------------------------------------------------

test('hint line shows branch and memory count once the store is read', async ($, on) => {
  drawHint(on)
  const { w } = await boot($, on)
  const ui = await $.ui.mount(HINT)
  expect((await ui.find({ type: 'Text' }))?.text).toBe('memoir: main · 18 memories')
  // The CLI is reached through the plugin's resolver, never bare `memoir`.
  const cliCalls = w.runs.filter(argv => argv.includes('get') || argv.includes('summarize'))
  expect(cliCalls.length).toBeGreaterThan(0)
  for (const argv of cliCalls) expect(argv[1]).toContain('scripts/memoir-cli.sh')
})

test('+N this turn appears when a capture lands after turn start, skips metrics, clears at the next turn', async ($, on) => {
  drawHint(on)
  const { w, clock } = await boot($, on)
  await $.turn.start({ text: 'remember to rebase', turnId: 't1' })

  // The Stop hook lands two commits a few seconds later: a metric and a fact.
  w.log =
    [
      line(5, 1700000500, 'Store metrics.turn.main in default'),
      line(4, 1700000450, 'Store preferences.tools.git in default'),
    ].join('\n') +
    '\n' +
    BASE_LOG
  w.mtime = 2000
  await clock.advance(3000)

  let ui = await $.ui.mount(HINT)
  expect((await ui.find({ type: 'Text' }))?.text).toBe('memoir: main · 18 memories · +1 this turn')

  await $.turn.start({ text: 'next', turnId: 't2' })
  ui = await $.ui.mount(HINT)
  expect((await ui.find({ type: 'Text' }))?.text).toBe('memoir: main · 18 memories')
})

test('no store: the hint stays silent and /memoir:pane answers in text', async ($, on) => {
  drawHint(on)
  await boot($, on, { exists: false })
  const ui = await $.ui.mount(HINT)
  expect((await ui.find({ type: 'Text' }))?.text).toBe('(no tail)')
  const ran = await runCommand($)
  expect(ran.text).toBe('No memoir store for this folder.')
})

test('statusline.sh already wired into settings: the hint adds nothing', async ($, on) => {
  drawHint(on)
  await boot($, on, {
    settings: { statusLine: { type: 'command', command: 'input=$(cat); printf "%s" "$input" | bash ~/.claude/plugins/cache/memoir/memoir/0.3.0/scripts/statusline.sh' } },
  })
  const ui = await $.ui.mount(HINT)
  expect((await ui.find({ type: 'Text' }))?.text).toBe('(no tail)')
})

test('non-drawing surface: /memoir:pane prints a plain-text summary', async ($, on) => {
  await boot($, on, { surfaces: [] })
  const ran = await runCommand($)
  expect(ran.text).toContain('memoir: main · 18 memories · 61 commits')
  expect(ran.text).toContain('workflow.coding.gates: Run make format')
  expect(ran.text).not.toContain('metrics.turn.main')
})

test('pane: recent feed hides metrics until toggled; taxonomy tab groups by first segment', async ($, on) => {
  await boot($, on)
  const ran = await runCommand($)
  expect(ran.text).toBe('memoir pane opened.')

  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Text', text: 'workflow.coding.gates' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Run make format/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'metrics.turn.main' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'main · 18 memories · 61 commits' })).toBeDefined()

  await ui.press({ key: 'metrics' })
  expect(await ui.find({ type: 'Text', text: 'metrics.turn.main' })).toBeDefined()
  await ui.press({ key: 'metrics' })

  await ui.press({ key: 'tab-taxonomy' })
  expect(await ui.find({ type: 'Button', text: /knowledge\s+3/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'group-metrics' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'decisions.architecture' })).toBeUndefined()
  await ui.press({ key: 'group-knowledge' })
  expect(await ui.find({ type: 'Text', text: 'decisions.architecture' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'technical.build' })).toBeDefined()
})

test('a content read that fails while the Stop hook is still writing is retried on the next refresh', async ($, on) => {
  const { w, clock } = await boot($, on, { cliFails: true })
  let ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Text', text: 'workflow.coding.gates' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /content unavailable/ })).toBeDefined()

  // The store settles; the next poll re-reads what it could not read before.
  await ui.unmount()
  w.cliFails = false
  w.mtime = 2000
  await clock.advance(3000)
  ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Text', text: /content unavailable/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Run make format/ })).toBeDefined()
})

test('turn metrics parse, format and scale', () => {
  const parsed = fmt.parseTurnMetrics(CONTENT['metrics.turn.main'])
  expect(parsed).toMatchObject({ turns: 22, toolCalls: 125, toolErrors: 0, latencyMs: 1470251, latencySamples: 22 })
  expect(fmt.parseTurnMetrics('not json')).toBeNull()
  expect(fmt.parseTurnMetrics(null)).toBeNull()
  expect(fmt.compactNumber(28285)).toBe('28k')
  expect(fmt.compactNumber(1470251)).toBe('1.5M')
  expect(fmt.compactNumber(95)).toBe('95')
  expect(fmt.bar(5, 10, 10)).toBe('█████')
  expect(fmt.bar(1, 1000, 10)).toBe('█')
  expect(fmt.bar(0, 10, 10)).toBe('')

  const charts = fmt.metricCharts(
    { main: parsed!, 'feat/x': fmt.parseTurnMetrics(CONTENT['metrics.turn.feat/x'])! },
    'feat/x',
  )
  expect(charts.map(c => c.title)).toEqual(['Turns', 'Tool calls', 'Tool errors', 'Avg latency (s)', 'Output chars', 'Tool result chars'])
  // The current branch leads every chart; the order is the same in each.
  expect(charts[0]!.rows.map(r => r.branch)).toEqual(['feat/x', 'main'])
  expect(charts[3]!.rows.map(r => r.label)).toEqual(['312.4', '66.8'])
  // No samples → no row, never a zero bar.
  const noLatency = fmt.metricCharts({ main: { ...parsed!, latencySamples: 0 } }, 'main')
  expect(noLatency[3]!.rows).toHaveLength(0)
})

test('metrics tab charts every branch with the current one first', async ($, on) => {
  await boot($, on)
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'tab-metrics' })
  expect(await ui.find({ type: 'Text', text: 'Turns' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Avg latency (s)' })).toBeDefined()
  const labels = await ui.findAll({ type: 'Text', text: /^[● ] (main|feat\/x)\s*$/ })
  expect(labels.length).toBe(12) // 6 charts × 2 branches
  expect(labels[0]!.text.trim()).toBe('● main')
  expect(labels[1]!.text.trim()).toBe('feat/x')
  expect(await ui.find({ type: 'Text', text: /^ 66\.8$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^ 312\.4$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^ 28k$/ })).toBeDefined()
})
