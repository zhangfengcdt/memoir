// memoir mod: a capture feed pane (/memoir:pane) and a status suffix on the
// prompt's hint line. Purely additive: the shell hooks in hooks.json keep
// doing capture and recall; the pane only writes what the person presses for
// (forget a key, restore main's value), through the same CLI.
//
// Design: the Stop hook captures asynchronously, so a turn's writes land in
// the store seconds after `turn.complete`. Instead of listening to turn
// events, the mod watches the store itself — a 3 s timer stats the current
// branch's ref (no subprocess) and re-reads git log + memory contents only
// when it changed. That catches every write path (Stop hook, /memoir:remember,
// the CLI, `memoir pull`).

import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type {
  MemoirBranchDiff,
  MemoirCapture,
  MemoirCommitDetail,
  MemoirMemories,
  MemoirMemory,
  MemoirMemoryAction,
  MemoirMergeState,
  MemoirMergeStrategy,
  MemoirStatus,
  MemoirTab,
  MemoirTurnMetrics,
} from '../../types'
import * as fmt from './format'
import { renderPane } from './pane'
import * as store from './store'

const PANE_ID = 'memoir'
const COMMAND = 'memoir:pane'
const POLL_MS = 3000
// The all-branches view lists this many branches, the most recently changed first.
const BRANCH_LIMIT = 10

// The drawn state, in `$.state` so a write redraws its readers and a hot reload
// keeps it. The engine reads these references off this file, so they live here.
const EMPTY_STATUS: MemoirStatus = { store: null, branch: null, head: null, memories: null, commits: null, commitsWithoutMetrics: null }
const status = atom({ plugin: 'memoir', key: 'status' } as const, EMPTY_STATUS)
const captures = atom({ plugin: 'memoir', key: 'captures' } as const, [] as MemoirCapture[])
const order = atom({ plugin: 'memoir', key: 'order' } as const, [] as string[])
const turnBaseline = atom({ plugin: 'memoir', key: 'turnBaseline' } as const, null as string | null)
const tab = atom({ plugin: 'memoir', key: 'tab' } as const, 'memories' as MemoirTab)
const showMetrics = atom({ plugin: 'memoir', key: 'showMetrics' } as const, false)
const showTaxonomy = atom({ plugin: 'memoir', key: 'showTaxonomy' } as const, false)
const expanded = atom({ plugin: 'memoir', key: 'expanded' } as const, [] as string[])
const taxonomy = atom({ plugin: 'memoir', key: 'taxonomy' } as const, {} as Record<string, number>)
const metrics = atom({ plugin: 'memoir', key: 'metrics' } as const, {} as Record<string, MemoirTurnMetrics>)
const memoryList = atom({ plugin: 'memoir', key: 'memories' } as const, { items: [], base: null } as MemoirMemories)
const filter = atom({ plugin: 'memoir', key: 'filter' } as const, '')
const selected = atom({ plugin: 'memoir', key: 'selected' } as const, null as string | null)
const selectedBranch = atom({ plugin: 'memoir', key: 'selectedBranch' } as const, null as string | null)
const allBranches = atom({ plugin: 'memoir', key: 'allBranches' } as const, false)
const branchList = atom({ plugin: 'memoir', key: 'branches' } as const, [] as MemoirBranchDiff[])
const armed = atom({ plugin: 'memoir', key: 'armed' } as const, null as MemoirMemoryAction | null)
const merge = atom({ plugin: 'memoir', key: 'merge' } as const, 'idle' as MemoirMergeState)
const pull = atom({ plugin: 'memoir', key: 'pull' } as const, 'idle' as MemoirMergeState)
const commit = atom({ plugin: 'memoir', key: 'commit' } as const, null as string | null)
const commitDetail = atom({ plugin: 'memoir', key: 'commitDetail' } as const, null as MemoirCommitDetail | null)

export const register: Register = on => {
  // Rebuilt by `session.start` (which a hot reload re-runs); the drawn state
  // lives in the `$.state` atoms above and survives a reload.
  let refresh: (force?: boolean) => Promise<void> = async () => undefined
  // The detail view's one write: forget the key, or put main's value back.
  let apply: (m: MemoirMemory, kind: MemoirMemoryAction) => Promise<string> = async () => 'memoir store not ready'
  // Merge the branch into main with one of the CLI's conflict strategies.
  let mergeNow: (strategy: MemoirMergeStrategy) => Promise<string> = async () => 'memoir store not ready'
  // Pull main into the branch: what main has that the branch does not, the same strategies.
  let pullNow: (strategy: MemoirMergeStrategy) => Promise<string> = async () => 'memoir store not ready'
  // What one commit changed, for the Recent tab's detail.
  let loadCommit: (sha: string) => Promise<MemoirCommitDetail> = async sha => ({ sha, changes: null })
  let hintSuppressed = false
  let home: string | null = null

  on('session.start', async ($, e, next) => {
    const host: store.Host = {
      root: $.plugin.root,
      run: (argv, init) => $.process.run(argv, init),
      read: path => $.fs.read(path),
      stat: path => $.fs.stat(path),
      exists: path => $.fs.exists(path),
    }

    let storePath: string | null = null
    try {
      storePath = (await $.env.get('MEMOIR_STORE')) || null
    } catch {
      // unset: derive it
    }
    if (!storePath) storePath = await store.deriveStore(host, e.cwd)
    try {
      home = (await $.env.get('HOME')) || null
    } catch {
      home = null
    }
    try {
      // The person already wires scripts/statusline.sh into their status line:
      // don't show memoir's state twice.
      hintSuppressed = fmt.usesStatuslineScript(await $.settings.read())
    } catch {
      hintSuppressed = false
    }

    let fingerprint = ''
    let inFlight: Promise<void> | null = null
    // Other branches' differences from main, kept until the branch or main moves.
    const branchCache = new Map<string, { tips: string; diff: MemoirBranchDiff }>()
    // While a merge checks main out and back, a poll would draw the wrong branch.
    let merging = false
    const contents = new Map<string, string | null>() // sha → stored text

    const doRefresh = async (force: boolean): Promise<void> => {
      if (!storePath || !(await store.storeExists(host, storePath))) {
        if ((await read($, status)).store !== null) await update($, status, () => EMPTY_STATUS)
        return
      }
      const path = storePath
      const everyBranch = await read($, allBranches)
      let fp = await store.fingerprint(host, path)
      // With every branch on view, any branch moving must redraw it too.
      const heads = everyBranch ? await store.listBranches(host, path) : []
      if (everyBranch) fp += '|' + heads.map(h => `${h.branch}@${h.tip}`).join(',')
      if (!force && fp === fingerprint) return
      fingerprint = fp

      const head = await store.readHead(host, path)
      // Off main the pane compares with main, and the Recent tab lists only
      // the commits not on it.
      const base = head.branch && head.branch !== 'main' ? 'main' : null
      const since = base && head.branch ? await store.mergedAt(host, path, base, head.branch) : null
      const log = await store.readLog(host, path, { base, since })
      // A miss is not cached: a refresh can fire while the Stop hook is still
      // writing, when `get` fails or finds nothing, so unknown contents are
      // asked for again on the next refresh (and on `r`).
      const missing = log.entries.filter(c => c.kind === 'store' && c.key !== null && !contents.has(c.sha))
      if (missing.length > 0) {
        const fetched = await store.fetchContents(
          host,
          path,
          missing.map(c => ({ key: c.key ?? '', namespace: c.namespace ?? 'default' })),
        )
        for (const c of missing) {
          const content = fetched.get(`${c.namespace}:${c.key}`)
          if (typeof content === 'string') contents.set(c.sha, content)
        }
      }
      for (const sha of [...contents.keys()]) if (!log.order.includes(sha)) contents.delete(sha)

      const memories = await store.readMemoryCount(host, path)
      const commits = await store.countCommits(host, path, { base, since })
      const commitsWithoutMetrics = await store.countCommits(host, path, { base, since }, false)
      const tree = await store.readTaxonomy(host, path)

      // Every default-namespace key's value, in one batched `get`: the Memories
      // tab lists them, and the per-branch turn accumulators among them feed
      // the Metrics tab. Read whole on each refresh since metrics change every turn.
      const keys = Object.keys(tree)
      const raw = await store.fetchContents(host, path, keys.map(key => ({ key, namespace: 'default' })))
      const current = new Map<string, string | null>()
      for (const key of keys) current.set(key, raw.get(`default:${key}`) ?? null)

      const turnMetrics: Record<string, MemoirTurnMetrics> = {}
      for (const key of keys) {
        if (!key.startsWith(fmt.TURN_METRICS_PREFIX)) continue
        const parsed = fmt.parseTurnMetrics(current.get(key))
        if (parsed) turnMetrics[key.slice(fmt.TURN_METRICS_PREFIX.length)] = parsed
      }

      // Off main, compare with main: the CLI's key-level diff reads both
      // commits from the tree (both values, never a checkout); a CLI without
      // it leaves the comparison to git history (which keys were written).
      const changes = base ? await store.readKeyChanges(host, path, base) : null
      const history = base && !changes ? await store.readBranchDiff(host, path, base, since) : null
      const compared: MemoirMemories = {
        items: fmt.diffMemories(keys, current, changes, history),
        base: changes || history ? base : null,
      }

      await update($, status, () => ({
        store: path,
        branch: head.branch,
        head: log.order[0] ?? null,
        memories,
        commits,
        commitsWithoutMetrics,
      }))
      await update($, order, () => log.order)
      await update($, captures, () => log.entries.map(c => ({ ...c, content: contents.get(c.sha) ?? null })))
      await update($, taxonomy, () => tree)
      await update($, metrics, () => turnMetrics)
      await update($, memoryList, () => compared)

      if (everyBranch) {
        const mainTip = heads.find(h => h.branch === 'main')?.tip ?? ''
        const diffs: MemoirBranchDiff[] = []
        for (const h of heads.filter(h => h.branch !== 'main').slice(0, BRANCH_LIMIT)) {
          const tips = `${h.tip}:${mainTip}`
          const cached = branchCache.get(h.branch)
          if (cached && cached.tips === tips) {
            diffs.push(cached.diff)
            continue
          }
          const exact = await store.readKeyChanges(host, path, 'main', h.branch)
          let diff: MemoirBranchDiff
          if (exact) diff = { branch: h.branch, at: h.at, items: fmt.itemsFromChanges(exact.values()), exact: true }
          else {
            const merged = await store.mergedAt(host, path, 'main', h.branch)
            const written = await store.readBranchDiff(host, path, 'main', merged, h.branch)
            diff = { branch: h.branch, at: h.at, items: written ? fmt.itemsFromHistory(written) : [], exact: false }
          }
          branchCache.set(h.branch, { tips, diff })
          diffs.push(diff)
        }
        await update($, branchList, () => diffs)
      }
    }

    refresh = (force = false) => {
      if (inFlight) return inFlight
      if (merging && !force) return Promise.resolve()
      inFlight = doRefresh(force)
        .catch(() => undefined)
        .finally(() => {
          inFlight = null
        })
      return inFlight
    }

    apply = async (m, kind) => {
      if (!storePath) return 'memoir store not ready'
      if (!fmt.memoryActions(m, (await read($, memoryList)).base).some(a => a.kind === kind)) return `nothing to do for ${m.key}`
      const error =
        kind === 'restore'
          ? await store.restoreKey(host, storePath, m.key, m.base ?? '')
          : await store.forgetKey(host, storePath, m.key)
      await refresh(true)
      return error ?? (kind === 'restore' ? `${m.key}: restored` : `${m.key}: forgotten`)
    }

    loadCommit = async sha => {
      if (!storePath) return { sha, changes: null }
      const changes = await store.readKeyChanges(host, storePath, `${sha}~1`, sha)
      return { sha, changes: changes ? [...changes.values()] : null }
    }

    mergeNow = async strategy => {
      const current = await read($, status)
      const base = (await read($, memoryList)).base
      if (!storePath || !current.branch) return 'memoir store not ready'
      if (!base) return 'nothing to merge: not on a branch compared with main'
      const values = new Map((await read($, memoryList)).items.map(m => [m.key, m.content]))
      merging = true
      try {
        return await store.mergeInto(host, storePath, current.branch, base, strategy, values)
      } finally {
        merging = false
        await refresh(true)
      }
    }

    pullNow = async strategy => {
      const current = await read($, status)
      const base = (await read($, memoryList)).base
      if (!storePath || !current.branch) return 'memoir store not ready'
      if (!base) return 'nothing to pull: not on a branch compared with main'
      // `both` appends main's value to the branch's: the base side of the comparison.
      const values = new Map((await read($, memoryList)).items.map(m => [m.key, m.base]))
      merging = true
      try {
        return await store.pullFrom(host, storePath, base, strategy, values)
      } finally {
        merging = false
        await refresh(true)
      }
    }

    void refresh(true)
    $.clock.every(POLL_MS, () => refresh())
    return next(e)
  })

  // /clear (and resume/fork) keep the module and its timer but start a new
  // conversation: drop the turn baseline so `+N this turn` does not carry over.
  on('classic.SessionStart', async ($, e, next) => {
    try {
      await update($, turnBaseline, () => null)
    } catch {
      // state unavailable: nothing to reset
    }
    void refresh(true)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.start', async ($, e, next) => {
    try {
      const current = await read($, status)
      await update($, turnBaseline, () => current.head)
    } catch {
      // state unavailable: the hint simply shows no `+N`
    }
    return next(e)
  })

  // The slash command is commands/pane.md, so it keeps the `/memoir:` prefix;
  // this hook answers it without running that prompt. On a Claude Code too
  // old to load mods the markdown runs as before and prints a text summary.
  on('command.run', { command: COMMAND }, async $ => {
    // Right after session start the first read may still be in flight (a `-p`
    // run gets here within milliseconds): wait for it so the answer is current.
    await refresh()
    const summary = async () => fmt.textSummary(await read($, status), await read($, captures), await $.clock.now())
    let surfaces: readonly string[] = []
    try {
      surfaces = await $.session.surfaces()
    } catch {
      // nothing draws: fall through to text
    }
    if (surfaces.length === 0) return { text: await summary() }
    if (!(await read($, status)).store) return { text: await summary() }
    const opened = await $.ui.open({ id: PANE_ID, title: 'memoir', focus: true })
    if (!opened.isPlaced) return { text: `${await summary()}\n\n(widen the terminal to show the memoir pane)` }
    void refresh(true)
    return { text: 'memoir pane opened.' }
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) =>
    renderPane({
      elements: $.ui.resolve(e),
      width: e.props.bodyColumns,
      now: await $.clock.now(),
      home,
      status: await read($, status),
      captures: await read($, captures),
      order: await read($, order),
      tab: await read($, tab),
      showMetrics: await read($, showMetrics),
      baseline: await read($, turnBaseline),
      taxonomy: await read($, taxonomy),
      metrics: await read($, metrics),
      memories: await read($, memoryList),
      filter: await read($, filter),
      selected: await read($, selected),
      selectedBranch: await read($, selectedBranch),
      allBranches: await read($, allBranches),
      branches: await read($, branchList),
      armed: await read($, armed),
      merge: await read($, merge),
      pull: await read($, pull),
      commit: await read($, commit),
      commitDetail: await read($, commitDetail),
      showTaxonomy: await read($, showTaxonomy),
      expanded: await read($, expanded),
      actions: {
        pickTab: next => update($, tab, () => next),
        toggleMetrics: () => update($, showMetrics, v => !v),
        toggleTaxonomy: () => update($, showTaxonomy, v => !v),
        setFilter: text => update($, filter, () => text),
        select: async (key, branch = null) => {
          await update($, armed, () => null)
          await update($, selectedBranch, () => (key === null ? null : branch))
          await update($, selected, () => key)
        },
        toggleAllBranches: async () => {
          await update($, allBranches, v => !v)
          await refresh(true)
        },
        arm: kind => update($, armed, () => kind),
        disarm: () => update($, armed, () => null),
        apply: async (m, kind) => {
          await update($, armed, () => null)
          await update($, selected, () => null)
          $.ui.toast(await apply(m, kind))
        },
        openCommit: async sha => {
          await update($, commitDetail, () => null)
          await update($, commit, () => sha)
          if (sha === null) return
          const detail = await loadCommit(sha)
          // Still the one open? A quick second click may have moved on.
          if ((await read($, commit)) === sha) await update($, commitDetail, () => detail)
        },
        openMerge: () => update($, merge, () => 'choose'),
        cancelMerge: () => update($, merge, () => 'idle'),
        runMerge: async strategy => {
          await update($, merge, () => 'running')
          const text = await mergeNow(strategy)
          await update($, merge, () => 'idle')
          $.ui.toast(text)
        },
        openPull: () => update($, pull, () => 'choose'),
        cancelPull: () => update($, pull, () => 'idle'),
        runPull: async strategy => {
          await update($, pull, () => 'running')
          const text = await pullNow(strategy)
          await update($, pull, () => 'idle')
          $.ui.toast(text)
        },
        toggleGroup: name =>
          update($, expanded, names => (names.includes(name) ? names.filter(n => n !== name) : [...names, name])),
        refresh: () => refresh(true),
      },
    }),
  )

  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    if (hintSuppressed) return next(e)
    const current = await read($, status)
    const list = await read($, captures)
    const shas = await read($, order)
    const baseline = await read($, turnBaseline)
    const tail = fmt.hintTail(current, fmt.newCount(list, shas, baseline))
    return tail === undefined ? next(e) : next({ ...e, props: { ...e.props, tail } })
  })
}
