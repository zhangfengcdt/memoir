// The pane's tree, built from plain values the render hook read: no `$` here,
// so the layout is a pure function of the view.

import type { EngineInterface, RenderElement } from 'claude-code'

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

export type PaneView = {
  elements: ReturnType<EngineInterface['ui']['resolve']>
  width: number
  now: number
  /** The person's home folder, for showing the store path as `~/…`; null when unknown. */
  home: string | null
  status: MemoirStatus
  captures: readonly MemoirCapture[]
  order: readonly string[]
  tab: MemoirTab
  showMetrics: boolean
  showTaxonomy: boolean
  baseline: string | null
  taxonomy: Readonly<Record<string, number>>
  metrics: Readonly<Record<string, MemoirTurnMetrics>>
  memories: MemoirMemories
  filter: string
  /** The key whose detail is open, or null for the list. */
  selected: string | null
  /** The branch that key belongs to in the all-branches view; null for the current branch. */
  selectedBranch: string | null
  allBranches: boolean
  branches: readonly MemoirBranchDiff[]
  /** The detail action pressed once, awaiting `y`; null when none. */
  armed: MemoirMemoryAction | null
  merge: MemoirMergeState
  pull: MemoirMergeState
  commit: string | null
  commitDetail: MemoirCommitDetail | null
  expanded: readonly string[]
  actions: {
    pickTab: (tab: MemoirTab) => unknown
    toggleMetrics: () => unknown
    toggleTaxonomy: () => unknown
    setFilter: (text: string) => unknown
    select: (key: string | null, branch?: string | null) => unknown
    toggleAllBranches: () => unknown
    arm: (kind: MemoirMemoryAction) => unknown
    disarm: () => unknown
    apply: (m: MemoirMemory, kind: MemoirMemoryAction) => unknown
    openCommit: (sha: string | null) => unknown
    openMerge: () => unknown
    cancelMerge: () => unknown
    runMerge: (strategy: MemoirMergeStrategy) => unknown
    openPull: () => unknown
    cancelPull: () => unknown
    runPull: (strategy: MemoirMergeStrategy) => unknown
    toggleGroup: (name: string) => unknown
    refresh: () => unknown
  }
}

/** What happens to a key changed on both sides: the CLI's `merge -S ours|theirs`, or both values kept. */
const STRATEGIES: { strategy: MemoirMergeStrategy; hotkey: string; what: string }[] = [
  { strategy: 'ours', hotkey: 'o', what: "keep main's value" },
  { strategy: 'theirs', hotkey: 't', what: "take this branch's value" },
  { strategy: 'both', hotkey: 'b', what: "keep main's value and append this branch's" },
]
/** The same choices pulling main into the branch: `ours` is the branch's side then. */
const PULL_STRATEGIES: { strategy: MemoirMergeStrategy; hotkey: string; what: string }[] = [
  { strategy: 'ours', hotkey: 'o', what: "keep this branch's value" },
  { strategy: 'theirs', hotkey: 't', what: "take main's value" },
  { strategy: 'both', hotkey: 'b', what: "keep this branch's value and append main's" },
]

const MARK_COLOR: Record<MemoirMemory['status'], string | undefined> = {
  added: 'diffAdded',
  changed: 'warning',
  removed: 'diffRemoved',
  same: undefined,
}

const AGE_WIDTH = 11
const INDENT = ' '.repeat(AGE_WIDTH + 3)

export function renderPane(view: PaneView): RenderElement {
  const { Box, Text, Button } = view.elements
  // The mobile app draws no field yet: there the filter row is left out.
  const Input = 'Input' in view.elements ? view.elements.Input : null
  const { status, actions } = view
  const width = Math.max(20, view.width)
  const open = new Set(view.expanded)

  // The mark on the left; title, tabs and status stacked beside it.
  const header = (
    <Box gap={2}>
      <Box flexDirection="column">
        {fmt.LOGO.map(line => (
          <Text color="claude">{line}</Text>
        ))}
      </Box>
      <Box flexDirection="column">
      {status.store ? (
        <Box gap={2}>
          <Text bold>memoir</Text>
          {/* logo, gaps and the title take the rest of the row */}
          <Text dimColor>{fmt.storeLabel(status.store, view.home, width - fmt.LOGO[0]!.length - 'memoir'.length - 4)}</Text>
        </Box>
      ) : (
        <Text bold>memoir</Text>
      )}
      <Box gap={2}>
        <Button key="tab-memories" plain hotkey="1" dimColor={view.tab === 'recent' || view.tab === 'metrics'} onPress={() => void actions.pickTab('memories')}>
          Memories
        </Button>
        <Button key="tab-recent" plain hotkey="2" dimColor={view.tab !== 'recent'} onPress={() => void actions.pickTab('recent')}>
          Recent
        </Button>
        <Button key="tab-metrics" plain hotkey="3" dimColor={view.tab !== 'metrics'} onPress={() => void actions.pickTab('metrics')}>
          Metrics
        </Button>
      </Box>
      {/* Each part of the status is a shortcut to the tab that explains it. */}
      <Box>
        {status.branch ? (
          <Button key="status-branch" plain dimColor onPress={() => void actions.pickTab('metrics')}>
            {status.branch}
          </Button>
        ) : (
          []
        )}
        {status.memories !== null ? (
          <Box>
            {status.branch ? <Text dimColor> · </Text> : []}
            <Button key="status-memories" plain dimColor onPress={() => void actions.pickTab('memories')}>
              {fmt.plural(status.memories, 'memory', 'memories')}
            </Button>
          </Box>
        ) : (
          []
        )}
        {status.commits !== null ? (
          <Box>
            {status.branch || status.memories !== null ? <Text dimColor> · </Text> : []}
            <Button key="status-commits" plain dimColor onPress={() => void actions.pickTab('recent')}>
              {fmt.commitsLabel(status, view.showMetrics) ?? ''}
            </Button>
          </Box>
        ) : (
          []
        )}
      </Box>
      </Box>
    </Box>
  )

  const metricsButton = (
    <Button key="metrics" plain hotkey="m" dimColor onPress={() => void actions.toggleMetrics()}>
      {`show metrics (${view.showMetrics ? 'on' : 'off'})`}
    </Button>
  )
  const refreshButton = (
    <Button key="refresh" plain hotkey="r" dimColor onPress={() => void actions.refresh()}>
      refresh
    </Button>
  )

  let body: RenderElement
  let footer: RenderElement
  if (!status.store) {
    body = <Text dimColor>No memoir store for this folder.</Text>
    footer = refreshButton
  } else if (view.tab === 'recent') {
    const fresh = fmt.newShas(view.order, view.baseline)
    const shown = fmt.visibleCaptures(view.captures, view.showMetrics)
    const open = view.commit === null ? undefined : view.captures.find(c => c.sha === view.commit)
    if (open) {
      // One commit: when it happened, and what it changed (both values from
      // the CLI's key-level diff), else the key's value as it is now.
      const detail = view.commitDetail?.sha === open.sha ? view.commitDetail : null
      const textWidth = Math.max(8, width - 2)
      const block = (text: string | null, sign: string, color: string | undefined) =>
        (text === null ? ['(content unavailable)'] : fmt.wrapText(text, textWidth, 200)).map(line => (
          <Text color={color} dimColor={text === null}>
            {`${sign} ${line}`}
          </Text>
        ))
      const changes = detail?.changes ?? null
      body = (
        <Box flexDirection="column">
          <Box>
            {fresh.has(open.sha) ? <Text color="success">● </Text> : <Text dimColor>○ </Text>}
            <Text bold>{open.subject}</Text>
          </Box>
          <Text dimColor>{`${open.sha.slice(0, 8)} · ${fmt.absoluteTime(open.at)} · ${fmt.relativeTime(view.now, open.at)}`}</Text>
          <Text> </Text>
          {detail === null ? (
            <Text dimColor>reading the commit…</Text>
          ) : changes === null ? (
            <Box flexDirection="column">
              {open.kind === 'store' ? (
                <Box flexDirection="column">
                  <Text dimColor>{`${open.key} now:`}</Text>
                  {block(open.content, ' ', undefined)}
                  <Text> </Text>
                  <Text dimColor>The change itself needs a memoir with key-level diffs; this is the key's current value.</Text>
                </Box>
              ) : (
                <Text dimColor>The change itself needs a memoir with key-level diffs.</Text>
              )}
            </Box>
          ) : changes.length === 0 ? (
            <Text dimColor>No memory changed in this commit.</Text>
          ) : (
            <Box flexDirection="column">
              {changes.map(c => (
                <Box flexDirection="column" marginBottom={1}>
                  <Box>
                    <Text color={c.operation === 'added' ? 'diffAdded' : c.operation === 'removed' ? 'diffRemoved' : 'warning'}>
                      {`${c.operation === 'added' ? '+' : c.operation === 'removed' ? '-' : '~'} `}
                    </Text>
                    <Text bold>{c.key}</Text>
                  </Box>
                  {c.operation === 'added' ? [] : block(c.old, '-', 'diffRemoved')}
                  {c.operation === 'removed' ? [] : block(c.new, '+', 'diffAdded')}
                </Box>
              ))}
            </Box>
          )}
        </Box>
      )
      footer = (
        <Box justifyContent="space-between">
          <Button key="back" plain hotkey="b" dimColor onPress={() => void actions.openCommit(null)}>
            back
          </Button>
          {refreshButton}
        </Box>
      )
    } else {
      body =
        shown.length === 0 ? (
          <Text dimColor>{status.branch && status.branch !== 'main' ? 'Nothing beyond main yet.' : 'No commits yet.'}</Text>
        ) : (
          <Box flexDirection="column">
            {shown.map(c => {
              const isNew = fresh.has(c.sha)
              const lines =
                c.kind !== 'store' ? [] : c.content ? fmt.wrapLines(c.content, width - INDENT.length, 2) : ['(content unavailable)']
              return (
                <Box flexDirection="column" marginBottom={1}>
                  <Button key={`commit-${c.sha}`} plain onPress={() => void actions.openCommit(c.sha)}>
                    {isNew ? <Text color="success">●</Text> : <Text dimColor>○</Text>}
                    <Text dimColor>{` ${fmt.relativeTime(view.now, c.at).padEnd(AGE_WIDTH)} `}</Text>
                    <Text bold>{c.subject}</Text>
                  </Button>
                  {lines.map(line => (
                    <Text dimColor>
                      {INDENT}
                      {line}
                    </Text>
                  ))}
                </Box>
              )
            })}
          </Box>
        )
      footer = (
        <Box justifyContent="space-between">
          <Box gap={3}>
            <Text dimColor>{`${status.branch && status.branch !== 'main' ? 'commits not on main · ' : ''}Enter/click a commit for its change`}</Text>
            {metricsButton}
          </Box>
          {refreshButton}
        </Box>
      )
    }
  } else if (view.tab !== 'metrics') {
    const { items, base } = view.memories
    // Machine-written `metrics.*` keys have their own tab; this one is for memories.
    const visible = fmt.visibleCaptures(items, false)
    const here = visible.filter(m => m.status !== 'removed')
    const differing = visible.filter(m => m.status !== 'same')
    const summary =
      base === null
        ? `${fmt.plural(here.length, 'memory', 'memories')}${status.branch === 'main' ? ' on main' : ' · no main branch to compare'}`
        : `${fmt.plural(here.length, 'memory', 'memories')} · ${differing.length === 1 ? '1 differs' : `${differing.length} differ`} from ${base}`
    // The open key: the current branch's, or another branch's (read-only).
    const elsewhere = view.selectedBranch === null ? undefined : view.branches.find(b => b.branch === view.selectedBranch)
    const current =
      view.selected === null
        ? undefined
        : elsewhere
          ? elsewhere.items.find(m => m.key === view.selected)
          : visible.find(m => m.key === view.selected)

    if (current) {
      // One key: its value, or both values when main's differs, and the one
      // write the person can ask for (behind a second press). Another
      // branch's key is shown the same way, with nothing to press.
      const available = elsewhere ? [] : fmt.memoryActions(current, base)
      const pending = view.armed === null ? undefined : available.find(a => a.kind === view.armed)
      const textWidth = Math.max(8, width - 2)
      const block = (text: string | null, sign: string, color: string | undefined) =>
        (text === null ? ['(content unavailable)'] : fmt.wrapText(text, textWidth, 200)).map(line => (
          <Text color={color} dimColor={text === null}>
            {`${sign} ${line}`}
          </Text>
        ))
      const branch = elsewhere ? elsewhere.branch : (status.branch ?? 'this branch')
      const against = elsewhere ? 'main' : base
      const explain =
        current.status === 'added'
          ? `new on ${branch}, not on ${against}`
          : current.status === 'changed'
            ? `changed on ${branch}; ${against} holds another value`
            : current.status === 'removed'
              ? `on ${against} only; forgotten on ${branch}`
              : against === null
                ? `on ${branch}`
                : `same on ${branch} and ${against}`
      body = (
        <Box flexDirection="column">
          <Box>
            <Text color={MARK_COLOR[current.status]}>{`${fmt.MARKS[current.status]} `}</Text>
            <Text bold>{current.key}</Text>
          </Box>
          <Text dimColor>{explain}</Text>
          <Text> </Text>
          {current.status === 'changed' || current.status === 'removed' ? (
            <Box flexDirection="column">
              <Text dimColor>{`${against}:`}</Text>
              {block(current.base, '-', 'diffRemoved')}
            </Box>
          ) : (
            []
          )}
          {current.status === 'changed' ? <Text> </Text> : []}
          {current.status === 'removed' ? (
            []
          ) : (
            <Box flexDirection="column">
              {current.status === 'same' ? [] : <Text dimColor>{`${branch}:`}</Text>}
              {block(current.content, current.status === 'same' ? ' ' : '+', current.status === 'same' ? undefined : 'diffAdded')}
            </Box>
          )}
          {(current.status === 'changed' || current.status === 'removed') && current.base === null ? (
            <Text dimColor>{`${against}'s value could not be read: update memoir for key-level diffs.`}</Text>
          ) : (
            []
          )}
        </Box>
      )
      footer = (
        <Box justifyContent="space-between">
          <Box gap={3}>
            <Button key="back" plain hotkey="b" dimColor onPress={() => void actions.select(null)}>
              back
            </Button>
            {pending ? (
              <Box gap={3}>
                <Button key="confirm" plain hotkey="y" onPress={() => void actions.apply(current, pending.kind)}>
                  {`confirm: ${pending.verb}`}
                </Button>
                <Button key="cancel" plain hotkey="n" dimColor onPress={() => void actions.disarm()}>
                  cancel
                </Button>
              </Box>
            ) : (
              available.map(a => (
                <Button key={`act-${a.kind}`} plain hotkey={a.hotkey} dimColor onPress={() => void actions.arm(a.kind)}>
                  {a.verb}
                </Button>
              ))
            )}
          </Box>
          {refreshButton}
        </Box>
      )
    } else if (view.pull === 'running') {
      body = <Text dimColor>{`Pulling ${base} into ${status.branch}…`}</Text>
      footer = <Text dimColor>the store stays on this branch</Text>
    } else if (view.pull === 'choose') {
      // What main has that this branch does not: new keys, and keys changed or forgotten here.
      const incoming = differing.filter(m => m.status !== 'added')
      body = (
        <Box flexDirection="column">
          <Text>{`Pull ${base} into ${status.branch}: ${incoming.length === 1 ? '1 key differs' : `${incoming.length} keys differ`} on ${base}.`}</Text>
          <Text dimColor>Keys changed only on main are applied either way; pick what to do with a key changed on both sides.</Text>
          <Text> </Text>
          {PULL_STRATEGIES.map(s => (
            <Button key={`pull-${s.strategy}`} plain hotkey={s.hotkey} onPress={() => void actions.runPull(s.strategy)}>
              {`${s.strategy.padEnd(7)}`}
              <Text dimColor>{s.what}</Text>
            </Button>
          ))}
        </Box>
      )
      footer = (
        <Button key="pull-cancel" plain hotkey="n" dimColor onPress={() => void actions.cancelPull()}>
          cancel
        </Button>
      )
    } else if (view.merge === 'running') {
      body = <Text dimColor>{`Merging ${status.branch} into ${base}…`}</Text>
      footer = <Text dimColor>the store is on main for a moment; it comes back by itself</Text>
    } else if (view.merge === 'choose') {
      body = (
        <Box flexDirection="column">
          <Text>{`Merge ${status.branch} into ${base}: ${differing.length === 1 ? '1 key differs' : `${differing.length} keys differ`}.`}</Text>
          <Text dimColor>Keys changed only here are applied either way; pick what to do with a key changed on both sides.</Text>
          <Text> </Text>
          {STRATEGIES.map(s => (
            <Button key={`strategy-${s.strategy}`} plain hotkey={s.hotkey} onPress={() => void actions.runMerge(s.strategy)}>
              {`${s.strategy.padEnd(7)}`}
              <Text dimColor>{s.what}</Text>
            </Button>
          ))}
        </Box>
      )
      footer = (
        <Button key="merge-cancel" plain hotkey="n" dimColor onPress={() => void actions.cancelMerge()}>
          cancel
        </Button>
      )
    } else {
      // Off main only what differs; on main (nothing to compare) every key.
      const shown = fmt.filterMemories(base === null ? visible : differing, view.filter)
      // Every other branch's differences from main, latest first; the current branch is the list above.
      const others = view.allBranches ? view.branches.filter(b => b.branch !== status.branch) : []
      const keyWidth = Math.min(
        40,
        Math.max(8, ...shown.map(m => m.key.length), ...others.flatMap(b => b.items.map(m => m.key.length))),
      )
      const snippetWidth = Math.max(8, width - 2 - keyWidth - 2)
      const row = (m: MemoirMemory, branch: string | null) => {
        const snippet = m.content ?? m.base
        return (
          <Button key={branch ? `mem-${branch}-${m.key}` : `mem-${m.key}`} plain onPress={() => void actions.select(m.key, branch)}>
            <Text color={MARK_COLOR[m.status]}>{`${fmt.MARKS[m.status]} `}</Text>
            <Text bold={m.status !== 'same'}>{m.key.padEnd(keyWidth).slice(0, keyWidth)}</Text>
            <Text dimColor>{`  ${snippet ? fmt.wrapLines(snippet, snippetWidth, 1)[0] ?? '' : '(content unavailable)'}`}</Text>
          </Button>
        )
      }
      const groups = view.showTaxonomy ? fmt.groupTaxonomy(view.taxonomy, false) : []
      body = (
        <Box flexDirection="column">
          <Text dimColor>{summary}</Text>
          {view.showTaxonomy ? (
            <Box flexDirection="column" marginBottom={1}>
              {groups.length === 0 ? (
                <Text dimColor>No taxonomy yet.</Text>
              ) : (
                groups.map(g => (
                  <Box flexDirection="column">
                    <Button key={`group-${g.name}`} plain onPress={() => void actions.toggleGroup(g.name)}>
                      {`${open.has(g.name) ? '▾' : '▸'} ${g.name.padEnd(12)} ${g.count}`}
                    </Button>
                    {open.has(g.name) ? g.leaves.map(leaf => <Text dimColor>{`    ${leaf.path}`}</Text>) : []}
                  </Box>
                ))
              )}
            </Box>
          ) : (
            []
          )}
          {Input ? (
            <Input
              key="filter"
              label="filter:"
              placeholder="type part of a key"
              value={view.filter}
              submitLabel="apply"
              onInput={(text: string) => void actions.setFilter(text)}
              onSubmit={(text: string) => void actions.setFilter(text)}
            />
          ) : (
            []
          )}
          {shown.length === 0 ? (
            <Text dimColor>
              {visible.length === 0 ? 'No memories yet.' : view.filter.trim() ? `No key contains "${view.filter.trim()}".` : `Nothing differs from ${base}.`}
            </Text>
          ) : (
            shown.map(m => row(m, null))
          )}
          {view.allBranches
            ? others.map(b => {
                const rows = fmt.filterMemories(fmt.visibleCaptures(b.items, false), view.filter)
                return (
                  <Box flexDirection="column" marginTop={1}>
                    <Box>
                      <Text bold>{b.branch}</Text>
                      <Text dimColor>
                        {` · ${rows.length === 1 ? '1 differs' : `${rows.length} differ`} from main · ${fmt.relativeTime(view.now, b.at)}${b.exact ? '' : ' · keys only'}`}
                      </Text>
                    </Box>
                    {rows.length === 0 ? <Text dimColor>  nothing</Text> : rows.map(m => row(m, b.branch))}
                  </Box>
                )
              })
            : []}
          {view.allBranches && others.length === 0 ? <Text dimColor>No other branch.</Text> : []}
        </Box>
      )
      footer = (
        <Box justifyContent="space-between">
          <Box gap={3}>
            {/* No letter hotkeys on these three: a click, or Tab and Enter, so a stray key never toggles them. */}
            <Button key="taxonomy" plain dimColor onPress={() => void actions.toggleTaxonomy()}>
              {`taxonomy (${view.showTaxonomy ? 'on' : 'off'})`}
            </Button>
            <Button key="all" plain dimColor onPress={() => void actions.toggleAllBranches()}>
              {`all branches (${view.allBranches ? 'on' : 'off'})`}
            </Button>
            {base !== null && differing.length > 0 ? (
              <Button key="merge" plain dimColor onPress={() => void actions.openMerge()}>
                {`merge to ${base} memory`}
              </Button>
            ) : (
              []
            )}
            {base !== null && differing.some(m => m.status !== 'added') ? (
              <Button key="pull" plain dimColor onPress={() => void actions.openPull()}>
                {`pull from ${base} memory`}
              </Button>
            ) : (
              []
            )}
          </Box>
          {refreshButton}
        </Box>
      )
    }
  } else {
    const charts = fmt.metricCharts(view.metrics, status.branch)
    const hasRows = charts.some(c => c.rows.length > 0)
    // One fixed label column across every chart, so the bars line up.
    const labelWidth = Math.min(24, Math.max(4, ...charts.flatMap(c => c.rows.map(r => r.branch.length))))
    const valueWidth = Math.max(1, ...charts.flatMap(c => c.rows.map(r => r.label.length)))
    const barWidth = Math.max(4, width - 2 - labelWidth - 2 - valueWidth)
    body = !hasRows ? (
      <Text dimColor>No turn metrics yet. They accumulate after each turn.</Text>
    ) : (
      <Box flexDirection="column">
        {charts.map(chart => {
          const max = Math.max(0, ...chart.rows.map(r => r.value))
          return (
            <Box flexDirection="column" marginBottom={1}>
              <Text bold>{chart.title}</Text>
              {chart.rows.map(row => (
                <Box>
                  <Text bold={row.isCurrent} dimColor={!row.isCurrent}>
                    {`${row.isCurrent ? '●' : ' '} ${fmt.wrapLines(row.branch, labelWidth, 1)[0]?.padEnd(labelWidth) ?? ''} `}
                  </Text>
                  <Text color={row.isCurrent ? 'claude' : 'inactive'}>{fmt.bar(row.value, max, barWidth).padEnd(barWidth)}</Text>
                  <Text dimColor>{` ${row.label}`}</Text>
                </Box>
              ))}
            </Box>
          )
        })}
      </Box>
    )
    footer = (
      <Box justifyContent="space-between">
        <Text dimColor>per branch, from metrics.turn.*</Text>
        {refreshButton}
      </Box>
    )
  }

  return (
    <Box flexDirection="column" width={width}>
      {header}
      <Box flexDirection="column" marginY={1}>
        {body}
      </Box>
      {footer}
    </Box>
  )
}
