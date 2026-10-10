// The pane's tree, built from plain values the render hook read: no `$` here,
// so the layout is a pure function of the view.

import type { EngineInterface, RenderElement } from 'claude-code'

import type { MemoirCapture, MemoirStatus, MemoirTab, MemoirTurnMetrics } from '../../types'
import * as fmt from './format'

export type PaneView = {
  elements: ReturnType<EngineInterface['ui']['resolve']>
  width: number
  rows: number
  now: number
  status: MemoirStatus
  captures: readonly MemoirCapture[]
  order: readonly string[]
  tab: MemoirTab
  showMetrics: boolean
  baseline: string | null
  taxonomy: Readonly<Record<string, number>>
  metrics: Readonly<Record<string, MemoirTurnMetrics>>
  expanded: readonly string[]
  actions: {
    pickTab: (tab: MemoirTab) => unknown
    toggleMetrics: () => unknown
    toggleGroup: (name: string) => unknown
    refresh: () => unknown
  }
}

const AGE_WIDTH = 11
const INDENT = ' '.repeat(AGE_WIDTH + 3)

export function renderPane(view: PaneView): RenderElement {
  const { Box, Text, Button } = view.elements
  const { status, actions } = view
  const width = Math.max(20, view.width)
  const rows = Math.max(6, view.rows)
  const open = new Set(view.expanded)

  const header = (
    <Box justifyContent="space-between">
      <Box gap={2}>
        <Button key="tab-recent" plain hotkey="1" dimColor={view.tab !== 'recent'} onPress={() => void actions.pickTab('recent')}>
          Recent
        </Button>
        <Button key="tab-taxonomy" plain hotkey="2" dimColor={view.tab !== 'taxonomy'} onPress={() => void actions.pickTab('taxonomy')}>
          Taxonomy
        </Button>
        <Button key="tab-metrics" plain hotkey="3" dimColor={view.tab !== 'metrics'} onPress={() => void actions.pickTab('metrics')}>
          Metrics
        </Button>
      </Box>
      <Text dimColor>{fmt.statusLine(status)}</Text>
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
    const limit = Math.max(1, Math.floor((rows - 3) / 3))
    body =
      shown.length === 0 ? (
        <Text dimColor>No captures yet.</Text>
      ) : (
        <Box flexDirection="column">
          {shown.slice(0, limit).map(c => {
            const isNew = fresh.has(c.sha)
            const lines = c.content ? fmt.wrapLines(c.content, width - INDENT.length, 2) : ['(content unavailable)']
            return (
              <Box flexDirection="column" marginBottom={1}>
                <Box>
                  {isNew ? <Text color="success">●</Text> : <Text dimColor>○</Text>}
                  <Text dimColor>{` ${fmt.relativeTime(view.now, c.at).padEnd(AGE_WIDTH)} `}</Text>
                  <Text bold>{c.key}</Text>
                </Box>
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
        {metricsButton}
        {refreshButton}
      </Box>
    )
  } else if (view.tab === 'metrics') {
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
  } else {
    const groups = fmt.groupTaxonomy(view.taxonomy, view.showMetrics)
    body =
      groups.length === 0 ? (
        <Text dimColor>No memories yet.</Text>
      ) : (
        <Box flexDirection="column">
          {groups.map(g => (
            <Box flexDirection="column">
              <Button key={`group-${g.name}`} plain onPress={() => void actions.toggleGroup(g.name)}>
                {`${open.has(g.name) ? '▾' : '▸'} ${g.name.padEnd(12)} ${g.count}`}
              </Button>
              {open.has(g.name) ? g.leaves.map(leaf => <Text dimColor>{`    ${leaf.path}`}</Text>) : []}
            </Box>
          ))}
        </Box>
      )
    footer = (
      <Box justifyContent="space-between">
        <Text dimColor>Tab/↑↓ move · Enter expand</Text>
        {metricsButton}
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
