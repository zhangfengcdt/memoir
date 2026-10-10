// memoir mod: a capture feed pane (/memoir:pane) and a status suffix on the
// prompt's hint line. Read-only and purely additive: the shell hooks in
// hooks.json keep doing capture and recall.
//
// Design: the Stop hook captures asynchronously, so a turn's writes land in
// the store seconds after `turn.complete`. Instead of listening to turn
// events, the mod watches the store itself — a 3 s timer stats the current
// branch's ref (no subprocess) and re-reads git log + memory contents only
// when it changed. That catches every write path (Stop hook, /memoir:remember,
// the CLI, `memoir pull`).

import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { MemoirCapture, MemoirStatus, MemoirTab, MemoirTurnMetrics } from '../../types'
import * as fmt from './format'
import { renderPane } from './pane'
import * as store from './store'

const PANE_ID = 'memoir'
const COMMAND = 'memoir:pane'
const POLL_MS = 3000

// The drawn state, in `$.state` so a write redraws its readers and a hot reload
// keeps it. The engine reads these references off this file, so they live here.
const EMPTY_STATUS: MemoirStatus = { store: null, branch: null, head: null, memories: null, commits: null }
const status = atom({ plugin: 'memoir', key: 'status' } as const, EMPTY_STATUS)
const captures = atom({ plugin: 'memoir', key: 'captures' } as const, [] as MemoirCapture[])
const order = atom({ plugin: 'memoir', key: 'order' } as const, [] as string[])
const turnBaseline = atom({ plugin: 'memoir', key: 'turnBaseline' } as const, null as string | null)
const tab = atom({ plugin: 'memoir', key: 'tab' } as const, 'recent' as MemoirTab)
const showMetrics = atom({ plugin: 'memoir', key: 'showMetrics' } as const, false)
const expanded = atom({ plugin: 'memoir', key: 'expanded' } as const, [] as string[])
const taxonomy = atom({ plugin: 'memoir', key: 'taxonomy' } as const, {} as Record<string, number>)
const metrics = atom({ plugin: 'memoir', key: 'metrics' } as const, {} as Record<string, MemoirTurnMetrics>)

export const register: Register = on => {
  // Rebuilt by `session.start` (which a hot reload re-runs); the drawn state
  // lives in the `$.state` atoms above and survives a reload.
  let refresh: (force?: boolean) => Promise<void> = async () => undefined
  let hintSuppressed = false

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
      // The person already wires scripts/statusline.sh into their status line:
      // don't show memoir's state twice.
      hintSuppressed = fmt.usesStatuslineScript(await $.settings.read())
    } catch {
      hintSuppressed = false
    }

    let fingerprint = ''
    let inFlight: Promise<void> | null = null
    const contents = new Map<string, string | null>() // sha → stored text

    const doRefresh = async (force: boolean): Promise<void> => {
      if (!storePath || !(await store.storeExists(host, storePath))) {
        if ((await read($, status)).store !== null) await update($, status, () => EMPTY_STATUS)
        return
      }
      const path = storePath
      const fp = await store.fingerprint(host, path)
      if (!force && fp === fingerprint) return
      fingerprint = fp

      const head = await store.readHead(host, path)
      const log = await store.readLog(host, path)
      // A miss is not cached: a refresh can fire while the Stop hook is still
      // writing, when `get` fails or finds nothing, so unknown contents are
      // asked for again on the next refresh (and on `r`).
      const missing = log.entries.filter(c => !contents.has(c.sha))
      if (missing.length > 0) {
        const fetched = await store.fetchContents(host, path, missing)
        for (const c of missing) {
          const content = fetched.get(`${c.namespace}:${c.key}`)
          if (typeof content === 'string') contents.set(c.sha, content)
        }
      }
      for (const sha of [...contents.keys()]) if (!log.order.includes(sha)) contents.delete(sha)

      const memories = await store.readMemoryCount(host, path)
      const commits = await store.countCommits(host, path)
      const tree = await store.readTaxonomy(host, path)

      // The per-branch turn accumulators change every turn, so they are read
      // whole on each refresh: one batched `get` for all of them.
      const metricKeys = Object.keys(tree).filter(k => k.startsWith(fmt.TURN_METRICS_PREFIX))
      const turnMetrics: Record<string, MemoirTurnMetrics> = {}
      if (metricKeys.length > 0) {
        const raw = await store.fetchContents(host, path, metricKeys.map(key => ({ key, namespace: 'default' })))
        for (const key of metricKeys) {
          const parsed = fmt.parseTurnMetrics(raw.get(`default:${key}`))
          if (parsed) turnMetrics[key.slice(fmt.TURN_METRICS_PREFIX.length)] = parsed
        }
      }

      await update($, status, () => ({ store: path, branch: head.branch, head: log.order[0] ?? null, memories, commits }))
      await update($, order, () => log.order)
      await update($, captures, () => log.entries.map(c => ({ ...c, content: contents.get(c.sha) ?? null })))
      await update($, taxonomy, () => tree)
      await update($, metrics, () => turnMetrics)
    }

    refresh = (force = false) => {
      if (inFlight) return inFlight
      inFlight = doRefresh(force)
        .catch(() => undefined)
        .finally(() => {
          inFlight = null
        })
      return inFlight
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
      rows: e.props.scroll.bodyRows,
      now: await $.clock.now(),
      status: await read($, status),
      captures: await read($, captures),
      order: await read($, order),
      tab: await read($, tab),
      showMetrics: await read($, showMetrics),
      baseline: await read($, turnBaseline),
      taxonomy: await read($, taxonomy),
      metrics: await read($, metrics),
      expanded: await read($, expanded),
      actions: {
        pickTab: next => update($, tab, () => next),
        toggleMetrics: () => update($, showMetrics, v => !v),
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
