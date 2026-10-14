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
  'knowledge.technical.build': 'pnpm 11 blocks build scripts unless whitelisted',
}

/** `memoir diff main HEAD` on the branch: both values of every key that differs, read without a checkout. */
const CHANGES_JSON = JSON.stringify({
  from: 'main',
  to: 'HEAD',
  diff: '',
  changes: [
    { namespace: 'default', key: 'knowledge.decisions.architecture', operation: 'modified', old: { content: 'Keep business logic in services/' }, new: { content: CONTENT['knowledge.decisions.architecture'] } },
    { namespace: 'default', key: 'knowledge.technical.build', operation: 'added', old: null, new: { content: CONTENT['knowledge.technical.build'] } },
    { namespace: 'default', key: 'preferences.tools.git', operation: 'removed', old: { content: CONTENT['preferences.tools.git'] }, new: null },
    { namespace: 'default', key: 'metrics.turn.feat/x', operation: 'added', old: null, new: { content: CONTENT['metrics.turn.feat/x'] } },
    { namespace: 'codebase:onboard', key: 'index', operation: 'added', old: null, new: { content: 'ignored: not the default namespace' } },
  ],
})

/** `memoir diff main feat/old`: an older branch's one difference. */
const OLD_CHANGES_JSON = JSON.stringify({
  from: 'main',
  to: 'feat/old',
  diff: '',
  changes: [{ namespace: 'default', key: 'a.b.c', operation: 'added', old: null, new: { content: 'only on the old branch' } }],
})

/** `git for-each-ref --sort=-committerdate`: main, then the branches, newest commit first. */
const REFS = ['feat/x\t1700000350\t' + sha(7), 'main\t1700000300\t' + sha(3), 'feat/old\t1699990000\t' + sha(5)].join('\n') + '\n'

/** Subjects of the commits this branch made since leaving main, and of main's own history (the fallback comparison). */
const BRANCH_SUBJECTS = ['Store knowledge.technical.build in default', 'Store knowledge.decisions.architecture in default', 'Store metrics.turn.main in default'].join('\n') + '\n'
const MAIN_SUBJECTS = ['Store workflow.coding.gates in default', 'Store knowledge.decisions.architecture in default', 'Store metrics.turn.main in default', 'Initialize memoir store'].join('\n') + '\n'

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
  /** `rev-list --count` without the metrics writes. */
  countNoMetrics: string
  cache: string
  head: string
  settings: Record<string, unknown>
  surfaces: string[]
  mtime: number
  /** mtime of `refs/heads/main`, watched while off main. */
  mainMtime: number
  placed: boolean
  cliFails: boolean
  /** A memoir CLI that predates key-level diffs: `diff` answers without `changes`. */
  oldCli: boolean
  /** ISO time of main's latest merge of this branch, when there was one. */
  mergedAt: string
  /** Subjects of the branch's commits after that merge. */
  afterMerge: string
  runs: string[][]
}

function world(on: On, overrides: Partial<World> = {}) {
  const w: World = {
    store: STORE,
    exists: true,
    log: BASE_LOG,
    count: '61\n',
    countNoMetrics: '61\n',
    cache: '18\n',
    head: 'ref: refs/heads/main\n',
    settings: {},
    surfaces: ['terminal'],
    mtime: 1000,
    mainMtime: 500,
    placed: true,
    cliFails: false,
    oldCli: false,
    mergedAt: '',
    afterMerge: '',
    runs: [],
    ...overrides,
  }
  const clock = mock.clock(on, { now: 1700000400_000 })
  mock.env(on, { HOME: '/home/u' })
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('settings.read', () => ({ value: w.settings }))
  on('session.surfaces', () => ({ value: w.surfaces as never }))
  on('ui.open', () => ({ value: (w.placed ? { isPlaced: true } : { isPlaced: false, reason: 'narrow' }) as never }))
  on('fs.exists', () => ({ value: w.exists }))
  on('fs.stat', ($, e) => ({
    value: { kind: 'file', size: 1, mtimeMs: e.path.endsWith('refs/heads/main') ? w.mainMtime : w.mtime, isLink: false },
  }))
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
    } else if (argv.includes('rev-list')) stdout = argv.includes('--invert-grep') ? w.countNoMetrics : w.count
    else if (argv.includes('for-each-ref')) stdout = REFS
    else if (argv.includes(' diff main feat/old')) stdout = w.oldCli ? JSON.stringify({ from: 'main', to: 'feat/old', diff: '' }) : OLD_CHANGES_JSON
    else if (argv.includes('--grep=')) stdout = w.mergedAt
    else if (argv.includes('--after=')) stdout = argv.includes('--format=%s') ? w.afterMerge : w.log
    else if (argv.includes('main..HEAD')) stdout = argv.includes('--format=%s') ? BRANCH_SUBJECTS : w.log
    else if (argv.includes(' log main ')) stdout = MAIN_SUBJECTS
    else if (argv.includes(' log ')) stdout = w.log
    else if (argv.includes(' get ') && w.cliFails) exitCode = 1
    else if (argv.includes(' get ')) {
      const keys = e.argv.slice(e.argv.indexOf('get') + 3)
      stdout = JSON.stringify({
        items: keys.map(key => ({ key, found: key in CONTENT, value: { content: CONTENT[key] } })),
      })
    } else if (argv.includes(' summarize ')) stdout = SUMMARY_JSON
    else if (argv.includes(' diff ') && argv.includes('~1')) {
      const to = e.argv[e.argv.length - 1]!
      stdout = w.oldCli
        ? JSON.stringify({ from: `${to}~1`, to, diff: '' })
        : JSON.stringify({
            from: `${to}~1`,
            to,
            diff: '',
            changes: [{ namespace: 'default', key: 'workflow.coding.gates', operation: 'modified', old: { content: 'Run make test before every commit' }, new: { content: CONTENT['workflow.coding.gates'] } }],
          })
    } else if (argv.includes(' diff ')) stdout = w.oldCli ? JSON.stringify({ from: 'main', to: 'HEAD', diff: '' }) : CHANGES_JSON
    else if (argv.includes(' forget ') || argv.includes(' remember ') || argv.includes(' checkout ')) stdout = JSON.stringify({ success: true })
    else if (argv.includes(' merge ')) stdout = JSON.stringify({ success: true, conflicts: ['default:knowledge.decisions.architecture'], commit_hash: 'abc' })
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

test('parseLog keeps every commit in order and recognises the keyed subjects', () => {
  const parsed = fmt.parseLog(BASE_LOG + line(9, 1700000900, 'Delete old.key from default') + '\n')
  expect(parsed.order).toEqual([sha(3), sha(2), sha(1), sha(0), sha(9)])
  expect(parsed.entries.map(c => [c.kind, c.key])).toEqual([
    ['store', 'metrics.turn.main'],
    ['store', 'workflow.coding.gates'],
    ['store', 'knowledge.decisions.architecture'],
    ['other', null],
    ['delete', 'old.key'],
  ])
  expect(parsed.entries[1]).toEqual({
    sha: sha(2),
    at: 1700000200,
    subject: 'Store workflow.coding.gates in default',
    kind: 'store',
    key: 'workflow.coding.gates',
    namespace: 'default',
  })
  expect(fmt.absoluteTime(0)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
})

test('metrics.* captures are hidden unless asked for', () => {
  const { entries } = fmt.parseLog(BASE_LOG)
  expect(fmt.visibleCaptures(entries, false).map(c => c.key)).toEqual([
    'workflow.coding.gates',
    'knowledge.decisions.architecture',
    null, // the first commit has no key and is never a metric
  ])
  expect(fmt.visibleCaptures(entries, true)).toHaveLength(4)
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
  const status = { store: STORE, branch: 'main', head: sha(3), memories: 18, commits: 61, commitsWithoutMetrics: 40 }
  expect(fmt.commitsLabel(status, false)).toBe('40 commits')
  expect(fmt.commitsLabel({ ...status, branch: 'feat/x' }, false)).toBe('+40 changes')
  expect(fmt.commitsLabel({ ...status, commitsWithoutMetrics: null }, false)).toBe('61 commits')
  // The plain-text summary lists non-metric commits, so its count leaves metrics out.
  expect(fmt.textSummary({ ...status, branch: 'feat/x' }, [], 0)).toContain('memoir: feat/x · 18 memories · +40 changes')
  expect(fmt.hintTail(status, 0)).toBe('memoir: main · 18 memories')
  expect(fmt.hintTail(status, 2)).toBe('memoir: main · 18 memories · +2 this turn')
  expect(fmt.hintTail({ ...status, memories: 1 }, 0)).toBe('memoir: main · 1 memory')
  expect(fmt.statusLine({ ...status, branch: 'feat/x', commits: 3 })).toBe('feat/x · 18 memories · +3 changes')
  expect(fmt.statusLine({ ...status, branch: 'feat/x', commits: 1 })).toBe('feat/x · 18 memories · +1 change')
  expect(fmt.statusLine({ ...status, branch: 'feat/x', commits: null })).toBe('feat/x · 18 memories')
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
  expect(ran.text).toContain('Store workflow.coding.gates in default: Run make format')
  expect(ran.text).not.toContain('metrics.turn.main')
})

test('pane: recent feed hides metrics until toggled; t shows the taxonomy above the keys', async ($, on) => {
  const { w } = await boot($, on)
  const ran = await runCommand($)
  expect(ran.text).toBe('memoir pane opened.')

  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Text', text: /differ from main|memories on main/ })).toBeDefined() // Memories opens first
  await ui.press({ key: 'tab-recent' })
  expect(await ui.find({ type: 'Button', key: `commit-${sha(2)}`, text: /Store workflow\.coding\.gates in default/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `commit-${sha(0)}`, text: /Initialize memoir store/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Run make format/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `commit-${sha(3)}` })).toBeUndefined()
  // The mark and the title head the pane.
  expect((await ui.findAll({ type: 'Text', text: /^[ ┏┓┛┗━]{9}$/ })).map(t => t.text)).toEqual([' ┏━━━━━┓ ', '┏┛┏┓ ┏┓┗┓', '┗━┛┗━┛┗━┛'])
  expect(await ui.find({ type: 'Text', text: 'memoir' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '~/.memoir/-proj' })).toBeDefined() // the store, beside the title
  expect(await ui.find({ type: 'Button', key: 'status-branch', text: 'main' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'status-memories', text: '18 memories' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'status-commits', text: '61 commits' })).toBeDefined()

  await ui.press({ key: 'metrics' })
  expect(await ui.find({ type: 'Button', key: `commit-${sha(3)}`, text: /metrics\.turn\.main/ })).toBeDefined()
  // On main the tab reads the latest ten commits.
  const log = w.runs.find(argv => argv.includes('--format=%H%x09%ct%x09%s'))
  expect(log!.slice(log!.indexOf('log'))).toEqual(['log', '--format=%H%x09%ct%x09%s', '-n', '10'])
  await ui.press({ key: 'metrics' })

  await ui.press({ key: 'tab-memories' })
  expect(await ui.find({ type: 'Button', key: 'tab-taxonomy' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'group-knowledge' })).toBeUndefined()
  await ui.press({ key: 'taxonomy' })
  expect(await ui.find({ type: 'Button', text: /knowledge\s+3/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'group-metrics' })).toBeUndefined()
  // Leaves are drawn indented; the key rows below hold the full keys.
  expect(await ui.find({ type: 'Text', text: /^    decisions\.architecture$/ })).toBeUndefined()
  await ui.press({ key: 'group-knowledge' })
  expect(await ui.find({ type: 'Text', text: /^    decisions\.architecture$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^    technical\.build$/ })).toBeDefined()
  // The keys are still listed under it.
  expect(await ui.find({ type: 'Button', key: 'mem-workflow.coding.gates' })).toBeDefined()
  await ui.press({ key: 'taxonomy' })
  expect(await ui.find({ type: 'Button', key: 'group-knowledge' })).toBeUndefined()
})

test('a content read that fails while the Stop hook is still writing is retried on the next refresh', async ($, on) => {
  const { w, clock } = await boot($, on, { cliFails: true })
  let ui = await $.ui.mount(PANE)
  await ui.press({ key: 'tab-recent' })
  expect(await ui.find({ type: 'Button', key: `commit-${sha(2)}` })).toBeDefined()
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

test('storeLabel shortens home to ~ and cuts long paths from the left', () => {
  expect(fmt.storeLabel('/home/u/.memoir/-proj', '/home/u', 80)).toBe('~/.memoir/-proj')
  expect(fmt.storeLabel('/home/u', '/home/u', 80)).toBe('~')
  expect(fmt.storeLabel('/home/u/.memoir/-proj', null, 80)).toBe('/home/u/.memoir/-proj')
  expect(fmt.storeLabel('/home/user2/.memoir/-proj', '/home/u', 80)).toBe('/home/user2/.memoir/-proj')
  expect(fmt.storeLabel('/home/u/.memoir/-Users-feng-githhub-memoir', '/home/u', 20)).toBe('…feng-githhub-memoir')
  expect(fmt.storeLabel('/home/u/.memoir/-proj', '/home/u', 1)).toBe('')
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

test('diffMemories: exact from the key-level diff, else from which keys the branch wrote', () => {
  const current = new Map<string, string | null>([
    ['a.b.c', 'same'],
    ['a.b.d', 'new here'],
    ['a.b.e', 'edited'],
  ])
  const changes = new Map([
    ['a.b.d', { key: 'a.b.d', operation: 'added' as const, old: null, new: 'new here' }],
    ['a.b.e', { key: 'a.b.e', operation: 'modified' as const, old: 'original', new: 'edited' }],
    ['a.b.z', { key: 'a.b.z', operation: 'removed' as const, old: 'gone here', new: null }],
  ])
  expect(fmt.diffMemories(['a.b.e', 'a.b.c', 'a.b.d'], current, changes, null)).toEqual([
    { key: 'a.b.c', content: 'same', base: null, status: 'same' },
    { key: 'a.b.d', content: 'new here', base: null, status: 'added' },
    { key: 'a.b.e', content: 'edited', base: 'original', status: 'changed' },
    { key: 'a.b.z', content: null, base: 'gone here', status: 'removed' },
  ])
  // No key-level diff: git history says what was written, main's values stay unknown.
  const history = { written: new Set(['a.b.d', 'a.b.e']), onBase: new Set(['a.b.c', 'a.b.e']) }
  expect(fmt.diffMemories(['a.b.e', 'a.b.c', 'a.b.d'], current, null, history)).toEqual([
    { key: 'a.b.c', content: 'same', base: null, status: 'same' },
    { key: 'a.b.d', content: 'new here', base: null, status: 'added' },
    { key: 'a.b.e', content: 'edited', base: null, status: 'changed' },
  ])
  expect(fmt.diffMemories(['a.b.d'], current, null, null)).toEqual([{ key: 'a.b.d', content: 'new here', base: null, status: 'same' }])
  expect(fmt.parseStoredKeys('Store x.y.z in default\nStore q in other\nMerge branch\n')).toEqual(new Set(['x.y.z']))

  expect(fmt.filterMemories([{ key: 'a.Build' }, { key: 'b.x' }], ' build ').map(m => m.key)).toEqual(['a.Build'])
  expect(fmt.filterMemories([{ key: 'a' }], '')).toHaveLength(1)
  expect(fmt.wrapText('one two\n\nthree', 5, 10)).toEqual(['one', 'two', '', 'three'])
  expect(fmt.itemsFromChanges([
    { key: 'z', operation: 'removed', old: 'gone', new: null },
    { key: 'a', operation: 'modified', old: 'before', new: 'after' },
  ])).toEqual([
    { key: 'a', content: 'after', base: 'before', status: 'changed' },
    { key: 'z', content: null, base: 'gone', status: 'removed' },
  ])
  expect(fmt.itemsFromHistory({ written: new Set(['b', 'a']), onBase: new Set(['b']) })).toEqual([
    { key: 'a', content: null, base: null, status: 'added' },
    { key: 'b', content: null, base: null, status: 'changed' },
  ])
  const changed = { key: 'k', content: 'new', base: 'old', status: 'changed' as const }
  const verbs = (m: Parameters<typeof fmt.memoryActions>[0], base: string | null) => fmt.memoryActions(m, base).map(a => [a.kind, a.verb])
  expect(verbs(changed, 'main')).toEqual([['forget', 'forget key'], ['restore', "restore main's value"]])
  expect(verbs({ ...changed, base: null }, 'main')).toEqual([['forget', 'forget key']])
  expect(verbs({ ...changed, status: 'removed' }, 'main')).toEqual([['restore', 'restore from main']])
  expect(verbs({ ...changed, status: 'removed', base: null }, 'main')).toEqual([])
  expect(verbs({ ...changed, status: 'added' }, 'main')).toEqual([['forget', 'forget key']])
  expect(verbs({ ...changed, status: 'same' }, null)).toEqual([['forget', 'forget key']])
})

test('memories tab (the default): on a branch only the keys that differ from main, removed ones included, filterable', async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)
  // Three keys live here; with the one main still holds, three differ.
  expect(await ui.find({ type: 'Text', text: '3 memories · 3 differ from main' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build', text: /^\+ knowledge\.technical\.build/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.decisions.architecture', text: /^~ knowledge\.decisions\.architecture/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-preferences.tools.git', text: /^- preferences\.tools\.git.*Prefer rebase/ })).toBeDefined()
  // Unchanged keys stay out of the branch view.
  expect(await ui.find({ type: 'Button', key: 'mem-workflow.coding.gates' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'mem-metrics.turn.feat/x' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'all', text: 'all branches (off)' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'merge', text: 'merge to main memory' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'pull', text: 'pull from main memory' })).toBeDefined()
  // Main is read through the CLI's key-level diff: never `get --branch` (the CLI would check main out).
  expect(w.runs.some(argv => argv.includes('diff') && argv.includes('main') && argv.includes('HEAD'))).toBe(true)
  expect(w.runs.some(argv => argv.includes('--branch'))).toBe(false)
  expect(w.runs.some(argv => argv.includes('main..HEAD') && argv.includes('--format=%s'))).toBe(false)

  await ui.input({ key: 'filter', text: 'BUILD', kind: 'change' })
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-preferences.tools.git' })).toBeUndefined()
  await ui.input({ key: 'filter', text: 'nothing-like-this', kind: 'change' })
  expect(await ui.find({ type: 'Text', text: /No key contains/ })).toBeDefined()
  await ui.input({ key: 'filter', text: '', kind: 'change' })
  // No metrics toggle here: `metrics.*` keys belong to the Metrics tab.
  expect(await ui.find({ type: 'Button', key: 'metrics' })).toBeUndefined()
})

test('a key opens to its change; forgetting or restoring it asks once more, then writes through the CLI', async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)

  // Changed: main's value and the branch's, then restore main's.
  await ui.press({ key: 'mem-knowledge.decisions.architecture' })
  expect(await ui.find({ type: 'Text', text: /changed on feat\/x; main holds another value/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '- Keep business logic in services/' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^\+ Keep business logic in services\/; CLI/ })).toBeDefined()
  // A changed key can be forgotten here or set back to main's value.
  expect(await ui.find({ type: 'Button', key: 'act-forget', text: 'forget key' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-restore', text: "restore main's value" })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'confirm' })).toBeUndefined()
  await ui.press({ key: 'act-restore' })
  expect(await ui.find({ type: 'Button', key: 'confirm', text: /confirm: restore main's value/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-forget' })).toBeUndefined()
  await ui.press({ key: 'cancel' })
  expect(await ui.find({ type: 'Button', key: 'confirm' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes('remember'))).toBe(false)
  await ui.press({ key: 'act-restore' })
  await ui.press({ key: 'confirm' })
  const restore = w.runs.find(argv => argv.includes('remember'))
  expect(restore).toBeDefined()
  expect(restore!.slice(restore!.indexOf('remember'))).toEqual(['remember', '-p', 'knowledge.decisions.architecture', '-n', 'default', '--replace', '--', 'Keep business logic in services/'])
  // Back on the list afterwards.
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build' })).toBeDefined()

  // Added: only the branch's value, and the key can be forgotten.
  await ui.press({ key: 'mem-knowledge.technical.build' })
  expect(await ui.find({ type: 'Text', text: /new on feat\/x, not on main/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^\+ pnpm 11 blocks/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-restore' })).toBeUndefined()
  await ui.press({ key: 'act-forget' })
  await ui.press({ key: 'confirm' })
  const forget = w.runs.find(argv => argv.includes('forget'))
  expect(forget!.slice(forget!.indexOf('forget'))).toEqual(['forget', '-n', 'default', '--force', '--', 'knowledge.technical.build'])

  // Removed: main's value only, restorable; `b` goes back without writing.
  await ui.press({ key: 'mem-preferences.tools.git' })
  expect(await ui.find({ type: 'Text', text: /on main only; forgotten on feat\/x/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '- Prefer rebase over merge for feature branches' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-restore', text: 'restore from main' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-forget' })).toBeUndefined()
  await ui.press({ key: 'back' })
  expect(await ui.find({ type: 'Button', key: 'mem-preferences.tools.git' })).toBeDefined()
})

test('memories tab on main lists everything; a key shows its value and can be forgotten', async ($, on) => {
  const { w } = await boot($, on)
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'tab-memories' })
  expect(await ui.find({ type: 'Text', text: '3 memories on main' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-workflow.coding.gates' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'merge' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'pull' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes('diff'))).toBe(false)
  expect(w.runs.some(argv => argv.includes('main..HEAD'))).toBe(false)

  await ui.press({ key: 'mem-workflow.coding.gates' })
  expect(await ui.find({ type: 'Text', text: 'on main' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^  Run make format, make lint/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-forget', text: 'forget key' })).toBeDefined()
  await ui.press({ key: 'act-forget' })
  await ui.press({ key: 'confirm' })
  expect(w.runs.some(argv => argv.includes('forget') && argv.includes('workflow.coding.gates'))).toBe(true)
})

test('a memoir CLI without key-level diffs: marks come from git history and main\'s values are not offered', async ($, on) => {
  const { w, clock } = await boot($, on, { head: 'ref: refs/heads/feat/x\n', oldCli: true })
  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Text', text: '3 memories · 2 differ from main' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build', text: /^\+ / })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.decisions.architecture', text: /^~ / })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-preferences.tools.git' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes('main..HEAD'))).toBe(true)

  await ui.press({ key: 'mem-knowledge.decisions.architecture' })
  expect(await ui.find({ type: 'Text', text: /could not be read/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-restore' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'act-forget' })).toBeDefined()
  await ui.press({ key: 'back' })

  // After a merge of this branch into main (one-parent merge commit, so
  // `main..HEAD` still lists everything) only the branch's later writes count.
  w.mergedAt = '2023-11-14T22:15:00+00:00\n'
  w.afterMerge = 'Store knowledge.technical.build in default\n'
  w.mtime = 2000
  await ui.unmount()
  await clock.advance(3000)
  const after = await $.ui.mount(PANE)
  expect(await after.find({ type: 'Text', text: '3 memories · 1 differs from main' })).toBeDefined()
  expect(await after.find({ type: 'Button', key: 'mem-knowledge.technical.build' })).toBeDefined()
  expect(await after.find({ type: 'Button', key: 'mem-knowledge.decisions.architecture' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes("--grep=Merge branch 'feat/x' into main"))).toBe(true)
  expect(w.runs.some(argv => argv.includes('--after=2023-11-14T22:15:00+00:00'))).toBe(true)
})

test('merge to main: pick one of the CLI merge strategies, the store comes back to the branch', async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'merge' })
  expect(await ui.find({ type: 'Text', text: /Merge feat\/x into main: 3 keys differ/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'strategy-ours' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'strategy-both', text: /append/ })).toBeDefined()
  await ui.press({ key: 'merge-cancel' })
  expect(await ui.find({ type: 'Button', key: 'strategy-ours' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes('merge'))).toBe(false)

  await ui.press({ key: 'merge' })
  await ui.press({ key: 'strategy-theirs' })
  const merge = w.runs.find(argv => argv.includes('merge'))
  expect(merge!.slice(merge!.indexOf('merge'))).toEqual(['merge', 'feat/x', '--into', 'main', '-S', 'theirs'])
  const back = w.runs.find(argv => argv.includes('checkout'))
  expect(back!.slice(back!.indexOf('checkout'))).toEqual(['checkout', 'feat/x'])
  expect(w.runs.indexOf(merge!)).toBeLessThan(w.runs.indexOf(back!))
  // The chooser closed and the list is back.
  expect(await ui.find({ type: 'Button', key: 'strategy-theirs' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build' })).toBeDefined()
})

test('merge with both: ours for the merge, then the branch value is appended on main before coming back', async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'merge' })
  await ui.press({ key: 'strategy-both' })
  const verbs = w.runs.map(argv => argv.find(a => ['merge', 'remember', 'checkout'].includes(a))).filter(Boolean)
  expect(verbs).toEqual(['merge', 'remember', 'checkout'])
  const merge = w.runs.find(argv => argv.includes('merge'))!
  expect(merge.slice(merge.indexOf('-S'))).toEqual(['-S', 'ours'])
  const append = w.runs.find(argv => argv.includes('remember'))!
  expect(append.slice(append.indexOf('remember'))).toEqual([
    'remember', '-p', 'knowledge.decisions.architecture', '-n', 'default', '--merge-policy', 'append', '--', CONTENT['knowledge.decisions.architecture'],
  ])
})

test('pull from main: the same chooser the other way round, merging main into the branch with no checkout', async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'pull' })
  // The key changed on both sides and the one main still holds; the branch's own new key is not main's to give.
  expect(await ui.find({ type: 'Text', text: /Pull main into feat\/x: 2 keys differ on main/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'pull-ours', text: /keep this branch's value/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'pull-both', text: /append main's/ })).toBeDefined()
  await ui.press({ key: 'pull-cancel' })
  expect(await ui.find({ type: 'Button', key: 'pull-ours' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes('merge'))).toBe(false)

  await ui.press({ key: 'pull' })
  await ui.press({ key: 'pull-theirs' })
  const merge = w.runs.find(argv => argv.includes('merge'))
  expect(merge!.slice(merge!.indexOf('merge'))).toEqual(['merge', 'main', '-S', 'theirs'])
  // Into the checked-out branch: nothing to check out and back.
  expect(w.runs.some(argv => argv.includes('checkout'))).toBe(false)
  expect(await ui.find({ type: 'Button', key: 'pull-theirs' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build' })).toBeDefined()
})

test("pull with both: ours for the merge, then main's value is appended on the branch", async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'pull' })
  await ui.press({ key: 'pull-both' })
  const verbs = w.runs.map(argv => argv.find(a => ['merge', 'remember', 'checkout'].includes(a))).filter(Boolean)
  expect(verbs).toEqual(['merge', 'remember'])
  const merge = w.runs.find(argv => argv.includes('merge'))!
  expect(merge.slice(merge.indexOf('merge'))).toEqual(['merge', 'main', '-S', 'ours'])
  const append = w.runs.find(argv => argv.includes('remember'))!
  expect(append.slice(append.indexOf('remember'))).toEqual([
    'remember', '-p', 'knowledge.decisions.architecture', '-n', 'default', '--merge-policy', 'append', '--', 'Keep business logic in services/',
  ])
})

test('a commit opens to what it changed, from the CLI diff of the commit against its parent', async ($, on) => {
  const { w } = await boot($, on)
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'tab-recent' })
  await ui.press({ key: `commit-${sha(2)}` })
  expect(await ui.find({ type: 'Text', text: 'Store workflow.coding.gates in default' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^0{8} · \d{4}-\d{2}-\d{2} \d{2}:\d{2} · 3 min ago$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '- Run make test before every commit' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '+ Run make format, make lint, make test before every commit' })).toBeDefined()
  const diff = w.runs.find(argv => argv.includes('diff') && argv.includes(`${sha(2)}~1`))
  expect(diff!.slice(diff!.indexOf('diff'))).toEqual(['diff', `${sha(2)}~1`, sha(2)])
  await ui.press({ key: 'back' })
  expect(await ui.find({ type: 'Button', key: `commit-${sha(2)}` })).toBeDefined()
})

test('a commit on a memoir without key-level diffs shows the key\'s current value instead', async ($, on) => {
  await boot($, on, { oldCli: true })
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'tab-recent' })
  await ui.press({ key: `commit-${sha(2)}` })
  expect(await ui.find({ type: 'Text', text: 'workflow.coding.gates now:' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^  Run make format, make lint/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /needs a memoir with key-level diffs/ })).toBeDefined()
})

test('recent tab on a branch lists only the commits not on main', async ($, on) => {
  const { w, clock } = await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const log = w.runs.find(argv => argv.includes('log') && argv.includes('--format=%H%x09%ct%x09%s'))
  expect(log!.slice(log!.indexOf('log'))).toEqual(['log', 'main..HEAD', '--format=%H%x09%ct%x09%s', '-n', '20'])
  const count = w.runs.find(argv => argv.includes('rev-list'))
  expect(count!.slice(count!.indexOf('rev-list'))).toEqual(['rev-list', '--count', 'main..HEAD'])
  let ui = await $.ui.mount(PANE)
  // The header counts what sits on top of main.
  expect(await ui.find({ type: 'Button', key: 'status-commits', text: '+61 changes' })).toBeDefined()
  await ui.press({ key: 'tab-recent' })
  expect(await ui.find({ type: 'Text', text: /^commits not on main/ })).toBeDefined()

  // Everything merged into main: the branch has nothing of its own to list.
  w.mergedAt = '2023-11-14T22:15:00+00:00\n'
  w.log = ''
  w.mtime = 2000
  await ui.unmount()
  await clock.advance(3000)
  const after = w.runs.filter(argv => argv.includes('--after=2023-11-14T22:15:00+00:00') && argv.includes('--format=%H%x09%ct%x09%s'))
  expect(after.length).toBeGreaterThan(0)
  ui = await $.ui.mount(PANE)
  await ui.press({ key: 'tab-recent' })
  expect(await ui.find({ type: 'Text', text: 'Nothing beyond main yet.' })).toBeDefined()
})

test('the header status is three shortcuts: branch to Metrics, memories to Memories, commits to Recent', async ($, on) => {
  await boot($, on)
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'status-branch' })
  expect(await ui.find({ type: 'Text', text: 'Turns' })).toBeDefined()
  await ui.press({ key: 'status-commits' })
  expect(await ui.find({ type: 'Button', key: `commit-${sha(2)}` })).toBeDefined()
  await ui.press({ key: 'status-memories' })
  expect(await ui.find({ type: 'Button', key: 'mem-workflow.coding.gates' })).toBeDefined()
})

test('the header count leaves metrics writes out while the Recent tab hides them', async ($, on) => {
  const { w } = await boot($, on, { head: 'ref: refs/heads/feat/x\n', count: '6\n', countNoMetrics: '1\n' })
  const filtered = w.runs.find(argv => argv.includes('rev-list') && argv.includes('--invert-grep'))
  expect(filtered!.slice(filtered!.indexOf('rev-list'))).toEqual([
    'rev-list', '--count', '--invert-grep', '--grep=^Store metrics\\.', '--grep=^Delete metrics\\.', 'main..HEAD',
  ])
  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Button', key: 'status-commits', text: '+1 change' })).toBeDefined()
  await ui.press({ key: 'tab-recent' })
  await ui.press({ key: 'metrics' })
  expect(await ui.find({ type: 'Button', key: 'status-commits', text: '+6 changes' })).toBeDefined()
})

test('off main, main moving (another process merging the branch) refreshes the view', async ($, on) => {
  const { w, clock } = await boot($, on, { head: 'ref: refs/heads/feat/x\n', count: '6\n', countNoMetrics: '1\n' })
  const before = w.runs.filter(argv => argv.includes('rev-list')).length
  // Nothing moved: a poll runs no git.
  await clock.advance(3000)
  expect(w.runs.filter(argv => argv.includes('rev-list')).length).toBe(before)
  // main took the branch: its ref is rewritten while HEAD and the branch ref stay.
  w.mainMtime = 900
  w.mergedAt = '2023-11-14T22:15:00+00:00\n'
  w.count = '0\n'
  w.countNoMetrics = '0\n'
  await clock.advance(3000)
  expect(w.runs.filter(argv => argv.includes('rev-list')).length).toBeGreaterThan(before)
  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Button', key: 'status-commits', text: '+0 changes' })).toBeDefined()
})

test('a lists every other branch\'s differences from main under the keys, latest branch first, read-only', async ($, on) => {
  const { w } = await boot($, on)
  const ui = await $.ui.mount(PANE)
  expect(await ui.find({ type: 'Button', key: 'all', text: 'all branches (off)' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-feat/x-knowledge.technical.build' })).toBeUndefined()
  expect(w.runs.some(argv => argv.includes('for-each-ref'))).toBe(false)

  await ui.press({ key: 'all' })
  expect(await ui.find({ type: 'Button', key: 'all', text: 'all branches (on)' })).toBeDefined()
  const refs = w.runs.find(argv => argv.includes('for-each-ref'))
  expect(refs!.slice(refs!.indexOf('for-each-ref'))).toEqual([
    'for-each-ref', '--sort=-committerdate', '--format=%(refname:short)%09%(committerdate:unix)%09%(objectname)', 'refs/heads',
  ])
  // One key-level diff per branch, main left out.
  expect(w.runs.filter(argv => argv.includes('diff') && argv.includes('feat/x')).length).toBe(1)
  expect(w.runs.filter(argv => argv.includes('diff') && argv.includes('feat/old')).length).toBe(1)
  expect(w.runs.some(argv => argv.includes('diff') && argv[argv.length - 1] === 'main')).toBe(false)

  // Sections in commit order, the newest branch on top, each with its count and age.
  const heads = await ui.findAll({ type: 'Text', text: /^(feat\/x|feat\/old)$/ })
  expect(heads.map(h => h.text)).toEqual(['feat/x', 'feat/old'])
  expect(await ui.find({ type: 'Text', text: /^ · 3 differ from main · / })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^ · 1 differs from main · /  })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-feat/x-preferences.tools.git', text: /^- preferences\.tools\.git/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-feat/old-a.b.c', text: /^\+ a\.b\.c.*only on the old branch/ })).toBeDefined()
  // Metrics keys stay out here too.
  expect(await ui.find({ type: 'Button', key: 'mem-feat/x-metrics.turn.feat/x' })).toBeUndefined()

  // Another branch's key opens read-only: both values, no action.
  await ui.press({ key: 'mem-feat/x-knowledge.decisions.architecture' })
  expect(await ui.find({ type: 'Text', text: /changed on feat\/x; main holds another value/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '- Keep business logic in services/' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'act-forget' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'act-restore' })).toBeUndefined()
  await ui.press({ key: 'back' })

  // The filter narrows every section.
  await ui.input({ key: 'filter', text: 'a.b', kind: 'change' })
  expect(await ui.find({ type: 'Button', key: 'mem-feat/old-a.b.c' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-feat/x-preferences.tools.git' })).toBeUndefined()
  await ui.input({ key: 'filter', text: '', kind: 'change' })

  await ui.press({ key: 'all' })
  expect(await ui.find({ type: 'Button', key: 'mem-feat/old-a.b.c' })).toBeUndefined()
})

test('on a branch, the all-branches view leaves that branch to the list above it', async ($, on) => {
  await boot($, on, { head: 'ref: refs/heads/feat/x\n' })
  const ui = await $.ui.mount(PANE)
  await ui.press({ key: 'all' })
  expect(await ui.find({ type: 'Button', key: 'mem-knowledge.technical.build' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'mem-feat/x-knowledge.technical.build' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'mem-feat/old-a.b.c' })).toBeDefined()
})
