// State contract for the memoir mod (hooks/mod/): the values it keeps in
// `$.state`, declared under the plugin's name so `claude plugin validate`
// can hold every `$.state` reference in the module to this shape.

/** One `Store <key> in <namespace>` commit of the memoir store. */
export type MemoirCapture = {
  sha: string
  /** Commit time, seconds since the epoch. */
  at: number
  key: string
  namespace: string
  /** The stored value's text, or null when it could not be read. */
  content: string | null
}

export type MemoirStatus = {
  /** The store's path once it resolved and exists; null otherwise. */
  store: string | null
  branch: string | null
  /** The head commit's sha, the baseline `turn.start` records. */
  head: string | null
  /** User-facing memory count, as the shell hooks cache it. */
  memories: number | null
  commits: number | null
}

/** One `metrics.turn.<branch>` accumulator the Stop hook maintains. */
export type MemoirTurnMetrics = {
  turns: number
  toolCalls: number
  toolErrors: number
  repeatedToolCalls: number
  outputChars: number
  toolInputChars: number
  toolResultChars: number
  latencyMs: number
  latencySamples: number
}

export type MemoirTab = 'recent' | 'taxonomy' | 'metrics'

declare module 'claude-code' {
  interface PluginState {
    memoir: {
      status: MemoirStatus
      /** Capture commits, newest first (last ~20 commits of the store). */
      captures: MemoirCapture[]
      /** Every sha in the same window, newest first, captures or not. */
      order: string[]
      /** The head sha when the current turn started; null before any turn. */
      turnBaseline: string | null
      tab: MemoirTab
      showMetrics: boolean
      /** Taxonomy groups (first path segment) the person has expanded. */
      expanded: string[]
      /** Full key → memory count, from `memoir summarize`. */
      taxonomy: Record<string, number>
      /** Branch → its turn accumulator, from the `metrics.turn.*` keys. */
      metrics: Record<string, MemoirTurnMetrics>
    }
  }
}
