// The one unit that reads the host: the store's git metadata through the
// filesystem and `git`, and memory contents through the plugin's CLI resolver
// (scripts/memoir-cli.sh), never a bare `memoir` — hook environments lack the
// venv PATH. `$` never crosses into this file (the engine refuses a passed
// `$`); the hook hands over closures as a `Host`. Every call swallows failure
// into "unknown".

import type { FsStat, ProcessRunInit, ProcessRunResult } from 'claude-code'

import type { MemoirKeyChange, MemoirMergeStrategy } from '../../types'
import { parseHead, parseLog, parseStoredKeys, type ParsedLog } from './format'

export type Host = {
  /** The plugin's folder (`$.plugin.root`). */
  root: string
  run: (argv: readonly string[], init: ProcessRunInit) => Promise<ProcessRunResult>
  read: (path: string) => Promise<unknown>
  stat: (path: string) => Promise<FsStat>
  exists: (path: string) => Promise<boolean>
}

const TIMEOUT_MS = 10_000
// A merge or a write on a large store can take a while; a kill mid-merge
// would leave the store on main.
const WRITE_TIMEOUT_MS = 180_000
// How many commits the Recent tab reads: on main the latest ten, on a branch up to twenty of its own.
const MAIN_LOG_WINDOW = 10
const BRANCH_LOG_WINDOW = 20

async function exec(host: Host, argv: readonly string[], cwd?: string, timeoutMs = TIMEOUT_MS): Promise<ProcessRunResult | null> {
  try {
    return await host.run(argv, { timeoutMs, ...(cwd ? { cwd } : {}) })
  } catch {
    return null
  }
}

async function run(host: Host, argv: readonly string[], cwd?: string): Promise<string | null> {
  const result = await exec(host, argv, cwd)
  return result && result.exitCode === 0 ? result.stdout : null
}

async function readText(host: Host, path: string): Promise<string> {
  const text = await host.read(path)
  return typeof text === 'string' ? text : ''
}

async function mtime(host: Host, path: string): Promise<number> {
  try {
    return (await host.stat(path)).mtimeMs
  } catch {
    return 0
  }
}

/** The store for `cwd`, by the same derivation the shell hooks use. */
export async function deriveStore(host: Host, cwd: string): Promise<string | null> {
  const out = await run(host, ['bash', `${host.root}/scripts/derive-store-path.sh`], cwd)
  const path = out?.trim()
  return path ? path : null
}

export async function storeExists(host: Host, store: string): Promise<boolean> {
  try {
    return await host.exists(`${store}/.git/HEAD`)
  } catch {
    return false
  }
}

export async function readHead(host: Host, store: string): Promise<{ branch: string | null; ref: string | null }> {
  try {
    return parseHead(await readText(host, `${store}/.git/HEAD`))
  } catch {
    return { branch: null, ref: null }
  }
}

/**
 * A cheap fingerprint of the store's head: changes whenever HEAD or the
 * checked-out branch's ref is rewritten (a capture, a checkout, a merge).
 * One small read and two stats; no subprocess.
 */
export async function fingerprint(host: Host, store: string): Promise<string> {
  const head = await readHead(host, store)
  const headMtime = await mtime(host, `${store}/.git/HEAD`)
  const refMtime = head.ref ? await mtime(host, `${store}/.git/${head.ref}`) : 0
  // Off main the view compares with main, so main moving (another worktree
  // or process merging this branch, say) must redraw it too.
  const mainMtime = head.branch && head.branch !== 'main' ? await mtime(host, `${store}/.git/refs/heads/main`) : 0
  const packedMtime = refMtime && (mainMtime || head.branch === 'main') ? 0 : await mtime(host, `${store}/.git/packed-refs`)
  return `${head.branch ?? ''}:${headMtime}:${refMtime}:${mainMtime}:${packedMtime}`
}

/** Which commits the Recent tab lists: on a branch, those not on `base` (after `since`, when main took a merge of the branch). */
export type LogScope = { base: string | null; since: string | null }

export async function readLog(host: Host, store: string, scope: LogScope = { base: null, since: null }): Promise<ParsedLog> {
  const range = scope.since ? ['HEAD', `--after=${scope.since}`] : scope.base ? [`${scope.base}..HEAD`] : []
  const window = scope.base || scope.since ? BRANCH_LOG_WINDOW : MAIN_LOG_WINDOW
  const out = await run(host, ['git', '-C', store, 'log', ...range, '--format=%H%x09%ct%x09%s', '-n', String(window)])
  return out ? parseLog(out) : { order: [], entries: [] }
}

/**
 * When `base` last took a merge of `branch`, as an ISO time, else null. A
 * memoir merge commit has one parent, so `base..HEAD` keeps listing the
 * merged commits; after that time only the branch's later commits count.
 */
export async function mergedAt(host: Host, store: string, base: string, branch: string): Promise<string | null> {
  const out = await run(host, [
    'git', '-C', store, 'log', base, '-n', '1', '--format=%cI', '--fixed-strings',
    `--grep=Merge branch '${branch}' into ${base}`,
  ])
  const at = out?.trim()
  return at ? at : null
}

/**
 * How many commits the Recent tab's scope holds: on a branch, those on top
 * of main; on main, all of them. With `metrics` false the machine-written
 * `metrics.*` commits are left out, as the tab leaves them out by default.
 */
export async function countCommits(
  host: Host,
  store: string,
  scope: LogScope = { base: null, since: null },
  metrics = true,
): Promise<number | null> {
  const range = scope.since ? ['HEAD', `--after=${scope.since}`] : scope.base ? [`${scope.base}..HEAD`] : ['HEAD']
  const filter = metrics ? [] : ['--invert-grep', '--grep=^Store metrics\\.', '--grep=^Delete metrics\\.']
  const out = await run(host, ['git', '-C', store, 'rev-list', '--count', ...filter, ...range])
  const n = Number(out?.trim())
  return out && Number.isFinite(n) ? n : null
}

/** The user-facing memory count the shell hooks cache after every capture. */
export async function readMemoryCount(host: Host, store: string): Promise<number | null> {
  try {
    const first = (await readText(host, `${store}/.git/plugin-statusline-cache`)).split('\n')[0] ?? ''
    const digits = first.replace(/\D/g, '')
    return digits ? Number(digits) : null
  } catch {
    return null
  }
}

function cli(host: Host, store: string): string[] {
  return ['bash', `${host.root}/scripts/memoir-cli.sh`, '--json', '-s', store]
}

/** Contents for the given keys, keyed `<namespace>:<key>`; one CLI call per namespace. */
export async function fetchContents(
  host: Host,
  store: string,
  entries: readonly { key: string; namespace: string }[],
): Promise<Map<string, string | null>> {
  const contents = new Map<string, string | null>()
  const byNamespace = new Map<string, Set<string>>()
  for (const entry of entries) {
    const keys = byNamespace.get(entry.namespace) ?? new Set<string>()
    keys.add(entry.key)
    byNamespace.set(entry.namespace, keys)
  }
  for (const [namespace, keys] of byNamespace) {
    const out = await run(host, [...cli(host, store), 'get', '-n', namespace, ...keys], store)
    if (!out) continue
    try {
      const parsed = JSON.parse(out) as { items?: { key: string; found: boolean; value?: { content?: unknown } }[] }
      for (const item of parsed.items ?? []) {
        const content = item.found && typeof item.value?.content === 'string' ? item.value.content : null
        contents.set(`${namespace}:${item.key}`, content)
      }
    } catch {
      // not JSON: leave these unknown
    }
  }
  return contents
}

/** Full key → count for the default namespace (deep enough that branch names with dots stay whole). */
export async function readTaxonomy(host: Host, store: string): Promise<Record<string, number>> {
  const out = await run(host, [...cli(host, store), 'summarize', '--depth', '8', '-n', 'default'], store)
  if (!out) return {}
  try {
    const parsed = JSON.parse(out) as { prefix_counts?: Record<string, Record<string, number>> }
    return parsed.prefix_counts?.['default'] ?? {}
  } catch {
    return {}
  }
}

/** Each found key's stored value (`value.value`) in one namespace, by key. */
async function readValues(host: Host, store: string, namespace: string, keys: readonly string[]): Promise<Map<string, unknown>> {
  const values = new Map<string, unknown>()
  const out = await run(host, [...cli(host, store), 'get', '-n', namespace, ...keys], store)
  if (!out) return values
  try {
    const parsed = JSON.parse(out) as { items?: { key: string; found: boolean; value?: { value?: unknown } }[] }
    for (const item of parsed.items ?? []) if (item.found) values.set(item.key, item.value?.value)
  } catch {
    // not JSON: nothing known
  }
  return values
}

/**
 * Every predefined taxonomy path (`<category>.<path>`) from the presets the
 * store has loaded (`taxonomy:v1:preset:*`, listed in `taxonomy:v1:index`),
 * sorted and deduplicated. Empty when the store has no taxonomy.
 */
export async function readPredefinedTaxonomy(host: Host, store: string): Promise<string[]> {
  const byType = (await readValues(host, store, 'taxonomy:v1:index', ['by-type'])).get('by-type') as { preset?: unknown } | undefined
  const listed = Array.isArray(byType?.preset) ? byType.preset.filter((id): id is string => typeof id === 'string') : []
  const ids = listed.length > 0 ? listed : ['simplified-preset']
  const paths = new Set<string>()
  for (const preset of (await readValues(host, store, 'taxonomy:v1:preset', ids)).values()) {
    if (!preset || typeof preset !== 'object') continue
    for (const [category, leaves] of Object.entries(preset as Record<string, unknown>)) {
      if (!Array.isArray(leaves)) continue
      for (const leaf of leaves) if (typeof leaf === 'string' && leaf) paths.add(`${category}.${leaf}`)
    }
  }
  return [...paths].sort()
}

/**
 * Which keys this branch wrote since it left main (`main..HEAD`, or after
 * `since` once main took a merge of the branch), and which keys main's own
 * history has ever stored: enough to tell what the branch added or changed,
 * from git metadata alone. Never `memoir get --branch`: the CLI routes that
 * by checking main out and back, and a Stop-hook write in that window lands
 * on main. Null when main cannot be compared.
 */
export async function readBranchDiff(
  host: Host,
  store: string,
  base: string,
  since: string | null,
  tip = 'HEAD',
): Promise<{ written: Set<string>; onBase: Set<string> } | null> {
  const written = since
    ? await run(host, ['git', '-C', store, 'log', tip, `--after=${since}`, '--format=%s'])
    : await run(host, ['git', '-C', store, 'log', `${base}..${tip}`, '--format=%s'])
  if (written === null) return null
  const onBase = await run(host, ['git', '-C', store, 'log', base, '--format=%s'])
  if (onBase === null) return null
  return { written: parseStoredKeys(written), onBase: parseStoredKeys(onBase) }
}

function contentOf(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object' && typeof (value as { content?: unknown }).content === 'string') {
    return (value as { content: string }).content
  }
  return null
}

/**
 * Every default-namespace key that differs between `from` and `to`, with
 * both values: `memoir diff <from> <to>`, which reads the two commits
 * straight from the tree and never checks anything out. Null when the CLI
 * predates key-level diffs (no `changes` in its answer) or fails; the caller
 * then falls back to the git-history comparison.
 */
export async function readKeyChanges(
  host: Host,
  store: string,
  from: string,
  to = 'HEAD',
): Promise<Map<string, MemoirKeyChange> | null> {
  const out = await run(host, [...cli(host, store), 'diff', from, to], store)
  if (!out) return null
  try {
    const parsed = JSON.parse(out) as {
      changes?: { namespace?: string; key?: string; operation?: string; old?: unknown; new?: unknown }[]
    }
    if (!Array.isArray(parsed.changes)) return null
    const changes = new Map<string, MemoirKeyChange>()
    for (const c of parsed.changes) {
      if (c.namespace !== 'default' || typeof c.key !== 'string') continue
      if (c.operation !== 'added' && c.operation !== 'modified' && c.operation !== 'removed') continue
      changes.set(c.key, { key: c.key, operation: c.operation, old: contentOf(c.old), new: contentOf(c.new) })
    }
    return changes
  } catch {
    return null
  }
}

function failure(result: ProcessRunResult | null, what: string): string | null {
  if (result && result.exitCode === 0) return null
  const detail = result ? (result.stderr || result.stdout).trim().split('\n').pop() ?? '' : 'could not run the memoir CLI'
  return `${what} failed${detail ? `: ${detail}` : ''}`
}

/** Delete `key` on the checked-out branch; the error text on failure, else null. */
export async function forgetKey(host: Host, store: string, key: string): Promise<string | null> {
  const result = await exec(host, [...cli(host, store), 'forget', '-n', 'default', '--force', '--', key], store, WRITE_TIMEOUT_MS)
  return failure(result, `forget ${key}`)
}

/** Write `content` at `key` on the checked-out branch, replacing what is there; the error text on failure, else null. */
export async function restoreKey(host: Host, store: string, key: string, content: string): Promise<string | null> {
  const result = await exec(
    host,
    [...cli(host, store), 'remember', '-p', key, '-n', 'default', '--replace', '--', content],
    store,
    WRITE_TIMEOUT_MS,
  )
  return failure(result, `restore ${key}`)
}

/**
 * Merge `source` into `target` (the checked-out branch when null) with the
 * CLI's native three-way merge. `ours` and `theirs` are the CLI's own
 * strategies, from the target's side; `both` merges with `ours` and then
 * appends the other side's value (from `values`) to each key the merge
 * reported as changed on both sides. Resolves to one line for a toast, or
 * the failure.
 */
async function runMerge(
  host: Host,
  store: string,
  source: string,
  target: string | null,
  strategy: MemoirMergeStrategy,
  values: ReadonlyMap<string, string | null>,
): Promise<{ text: string; failed: string | null }> {
  const native = strategy === 'both' ? 'ours' : strategy
  const into = target === null ? [] : ['--into', target]
  const merged = await exec(host, [...cli(host, store), 'merge', source, ...into, '-S', native], store, WRITE_TIMEOUT_MS)
  let parsed: { conflicts?: unknown; error?: unknown } = {}
  try {
    parsed = JSON.parse(merged?.stdout ?? '') as typeof parsed
  } catch {
    // not JSON: the exit code tells
  }
  const conflicts = (Array.isArray(parsed.conflicts) ? parsed.conflicts : [])
    .filter((k): k is string => typeof k === 'string' && k.startsWith('default:'))
    .map(k => k.slice('default:'.length))

  let appended = 0
  let unappended = 0
  if (merged && merged.exitCode === 0 && strategy === 'both') {
    for (const key of conflicts) {
      const content = values.get(key)
      if (content === null || content === undefined) {
        unappended += 1
        continue
      }
      const result = await exec(
        host,
        [...cli(host, store), 'remember', '-p', key, '-n', 'default', '--merge-policy', 'append', '--', content],
        store,
        WRITE_TIMEOUT_MS,
      )
      if (result && result.exitCode === 0) appended += 1
      else unappended += 1
    }
  }

  const what = target === null ? `merge of ${source}` : `merge into ${target}`
  const failed = failure(merged, what)
  if (failed) return { text: '', failed: typeof parsed.error === 'string' ? `${what} failed: ${parsed.error}` : failed }
  const n = conflicts.length
  const both = `${appended} appended${unappended ? `, ${unappended} not appended` : ''}`
  const resolved = n ? `, ${n} ${n === 1 ? 'key' : 'keys'} changed on both sides: ${strategy === 'both' ? both : strategy}` : ''
  return { text: `${target === null ? 'pulled' : 'merged'} ${source} into ${target ?? 'this branch'}${resolved}`, failed: null }
}

/**
 * Merge `source` into `target`, then check `source` out again: `merge --into`
 * leaves the store on the target. `values` holds the branch's values, which
 * `both` appends to main's.
 */
export async function mergeInto(
  host: Host,
  store: string,
  source: string,
  target: string,
  strategy: MemoirMergeStrategy,
  values: ReadonlyMap<string, string | null>,
): Promise<string> {
  const result = await runMerge(host, store, source, target, strategy, values)
  const back = await exec(host, [...cli(host, store), 'checkout', source], store, WRITE_TIMEOUT_MS)
  if (result.failed) return result.failed
  const stuck = failure(back, `checkout ${source}`)
  return stuck ? `${result.text}; ${stuck}` : result.text
}

/**
 * Pull `source` (main) into the checked-out branch: the same three-way merge
 * the other way round, with no checkout, so a capture landing meanwhile stays
 * on the branch. `values` holds main's values, which `both` appends to the
 * branch's.
 */
export async function pullFrom(
  host: Host,
  store: string,
  source: string,
  strategy: MemoirMergeStrategy,
  values: ReadonlyMap<string, string | null>,
): Promise<string> {
  const result = await runMerge(host, store, source, null, strategy, values)
  return result.failed ?? result.text
}

export type BranchHead = { branch: string; at: number; tip: string }

/** Every local branch, the most recently committed first. */
export async function listBranches(host: Host, store: string): Promise<BranchHead[]> {
  const out = await run(host, [
    'git', '-C', store, 'for-each-ref', '--sort=-committerdate',
    '--format=%(refname:short)%09%(committerdate:unix)%09%(objectname)', 'refs/heads',
  ])
  if (!out) return []
  const heads: BranchHead[] = []
  for (const line of out.split('\n')) {
    const [branch, ct, tip] = line.split('\t')
    const at = Number(ct)
    if (branch && tip && Number.isFinite(at)) heads.push({ branch, at, tip })
  }
  return heads
}
