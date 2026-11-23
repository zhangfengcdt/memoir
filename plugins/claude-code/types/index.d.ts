// State contract for the memoir mod (hooks/mod/): the values it keeps in
// `$.state`, declared under the plugin's name so `claude plugin validate`
// can hold every `$.state` reference in the module to this shape.

/** One commit of the memoir store, newest first in the Recent tab. */
export type MemoirCapture = {
  sha: string
  /** Commit time, seconds since the epoch. */
  at: number
  /** The commit's title (`Store <key> in <namespace>`, `Delete …`, `Merge branch …`). */
  subject: string
  /** `store` and `delete` name a key; anything else (a merge, the first commit) is `other`. */
  kind: 'store' | 'delete' | 'other'
  key: string | null
  namespace: string | null
  /** The stored value's text for a `store` commit, or null when it could not be read. */
  content: string | null
}

/** What one commit changed, as `memoir diff <sha>~1 <sha>` reports it. */
export type MemoirCommitDetail = {
  sha: string
  /** Null when the CLI cannot diff commits (older memoir, or the first commit). */
  changes: MemoirKeyChange[] | null
}

export type MemoirStatus = {
  /** The store's path once it resolved and exists; null otherwise. */
  store: string | null
  branch: string | null
  /** The head commit's sha, the baseline `turn.start` records. */
  head: string | null
  /** User-facing memory count, as the shell hooks cache it. */
  memories: number | null
  /** On a branch, the commits on top of main (after main's latest merge of the branch); on main, all commits. */
  commits: number | null
  /** The same count without the `metrics.*` writes: what the Recent tab lists while metrics are hidden. */
  commitsWithoutMetrics: number | null
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

/** One memory key on the current branch, compared with the same key on main. */
export type MemoirMemory = {
  key: string
  /** The value on the current branch; null when the key is not here (`removed`) or unreadable. */
  content: string | null
  /** The value on the compared branch (main) when it could be read; null otherwise. */
  base: string | null
  /** `added`: not on main; `changed`: on main with another value; `removed`: on main only; else `same`. */
  status: 'same' | 'added' | 'changed' | 'removed'
}

/** One key's change between the compared branch and HEAD, as `memoir diff` reports it. */
export type MemoirKeyChange = {
  key: string
  operation: 'added' | 'modified' | 'removed'
  /** The stored text on the compared branch, null when absent there. */
  old: string | null
  /** The stored text on HEAD, null when absent here. */
  new: string | null
}

export type MemoirMemories = {
  items: MemoirMemory[]
  /** The branch the items were compared with (`main`), or null when no comparison ran. */
  base: string | null
}

/** One branch's keys that differ from main, for the Memories tab's all-branches view. */
export type MemoirBranchDiff = {
  branch: string
  /** Its last commit, seconds since the epoch. */
  at: number
  /** Only the keys that differ from main (`added`, `changed`, `removed`). */
  items: MemoirMemory[]
  /** True when both values were read (the CLI's key-level diff); false from git history alone. */
  exact: boolean
}

export type MemoirTab = 'memories' | 'recent' | 'metrics'

/**
 * What to do with a key changed on both the branch and main: `ours` and
 * `theirs` are `memoir merge -S`, from the target's point of view; `both`
 * keeps the target's value and appends the other side's to it.
 */
export type MemoirMergeStrategy = 'ours' | 'theirs' | 'both'

/** What the Memories detail can do to a key: delete it here, or write main's value back. */
export type MemoirMemoryAction = 'forget' | 'restore'

/** The Memories tab's merge-to-main and pull-from-main flows: closed, picking a strategy, or running. */
export type MemoirMergeState = 'idle' | 'choose' | 'running'

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
      /** Memories tab: the taxonomy block above the keys is shown. */
      showTaxonomy: boolean
      /** Taxonomy groups (first path segment) the person has expanded. */
      expanded: string[]
      /** Full key → memory count, from `memoir summarize`. */
      taxonomy: Record<string, number>
      /** The store's predefined taxonomy paths (`<category>.<path>`, from `taxonomy:v1:preset:*`), read once per store. */
      predefinedTaxonomy: { store: string | null; paths: string[] }
      /** Branch → its turn accumulator, from the `metrics.turn.*` keys. */
      metrics: Record<string, MemoirTurnMetrics>
      /** Every key on the branch with its value and how it compares with main. */
      memories: MemoirMemories
      /** Memories tab: the key filter the person typed. */
      filter: string
      /** Memories tab: the key whose detail is open, or null for the list. */
      selected: string | null
      /** Memories tab: the branch the open key belongs to in the all-branches view; null for the current branch. */
      selectedBranch: string | null
      /** Memories tab: every branch's differences from main are listed under the current one. */
      allBranches: boolean
      /** The ten most recently changed branches other than main, latest first, each with its differences from main. */
      branches: MemoirBranchDiff[]
      /** Memories tab: the detail action that awaits its confirmation, if any. */
      armed: MemoirMemoryAction | null
      /** Memories tab: where the merge-to-main flow stands. */
      merge: MemoirMergeState
      /** Memories tab: where the pull-from-main flow stands. */
      pull: MemoirMergeState
      /** Recent tab: the sha whose detail is open, or null for the list. */
      commit: string | null
      /** Recent tab: the open commit's changes once read; null while loading. */
      commitDetail: MemoirCommitDetail | null
    }
  }
}
