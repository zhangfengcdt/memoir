// The one unit that reads the host: the store's git metadata through the
// filesystem and `git`, and memory contents through the plugin's CLI resolver
// (scripts/memoir-cli.sh), never a bare `memoir` — hook environments lack the
// venv PATH. `$` never crosses into this file (the engine refuses a passed
// `$`); the hook hands over closures as a `Host`. Every call swallows failure
// into "unknown".

import type { FsStat, ProcessRunInit, ProcessRunResult } from 'claude-code'

import { parseHead, parseLog, type ParsedLog } from './format'

export type Host = {
  /** The plugin's folder (`$.plugin.root`). */
  root: string
  run: (argv: readonly string[], init: ProcessRunInit) => Promise<ProcessRunResult>
  read: (path: string) => Promise<unknown>
  stat: (path: string) => Promise<FsStat>
  exists: (path: string) => Promise<boolean>
}

const TIMEOUT_MS = 10_000
const LOG_WINDOW = 20

async function run(host: Host, argv: readonly string[], cwd?: string): Promise<string | null> {
  try {
    const result = await host.run(argv, { timeoutMs: TIMEOUT_MS, ...(cwd ? { cwd } : {}) })
    return result.exitCode === 0 ? result.stdout : null
  } catch {
    return null
  }
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
  const packedMtime = refMtime ? 0 : await mtime(host, `${store}/.git/packed-refs`)
  return `${head.branch ?? ''}:${headMtime}:${refMtime}:${packedMtime}`
}

export async function readLog(host: Host, store: string): Promise<ParsedLog> {
  const out = await run(host, ['git', '-C', store, 'log', '--format=%H%x09%ct%x09%s', '-n', String(LOG_WINDOW)])
  return out ? parseLog(out) : { order: [], entries: [] }
}

export async function countCommits(host: Host, store: string): Promise<number | null> {
  const out = await run(host, ['git', '-C', store, 'rev-list', '--count', 'HEAD'])
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
