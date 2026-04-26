import { useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type {
  MetricsItem,
  MetricsResponse,
  OnboardItem,
  OnboardResponse,
  StatisticsBlock,
  StatisticsResponse,
  StatsSection,
} from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "./StatsModal.css";

type SectionKey = keyof StatisticsBlock;
type TabKey = SectionKey | "overview" | "onboard" | "metrics";

const BASE_SECTIONS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "storage", label: "Storage" },
  { key: "tree_structure", label: "Tree" },
  { key: "versioning", label: "Versioning" },
  { key: "performance", label: "Performance" },
  { key: "taxonomy", label: "Taxonomy" },
  { key: "content", label: "Content" },
  { key: "metadata", label: "Metadata" },
  { key: "system", label: "System" },
];

export default function StatsModal() {
  const open = useUI((s) => s.statsOpen);
  const close = useUI((s) => s.closeStats);
  const storePath = useStore((s) => s.storePath);

  const [data, setData] = useState<StatisticsResponse | null>(null);
  const [onboardData, setOnboardData] = useState<OnboardResponse | null>(null);
  const [metricsData, setMetricsData] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  // Fetch when modal opens; abandon when it closes. Onboard + metrics fetch
  // in parallel with the main statistics call so the dialog renders without
  // a second loading flash. Both surface as empty-state on failure rather
  // than blocking the rest of the modal — they're optional add-ons.
  useEffect(() => {
    if (!open || !storePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setOnboardData(null);
    setMetricsData(null);
    api
      .statistics(storePath)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof MemoirApiError ? err.message : String(err));
        setLoading(false);
      });
    api
      .onboard(storePath)
      .then((res) => {
        if (!cancelled) setOnboardData(res);
      })
      .catch(() => {
        /* optional — keep tab hidden on failure */
      });
    api
      .metrics(storePath)
      .then((res) => {
        if (!cancelled) setMetricsData(res);
      })
      .catch(() => {
        /* optional — keep tab hidden on failure */
      });
    return () => {
      cancelled = true;
    };
  }, [open, storePath]);

  // Focus management: trap focus inside the dialog while open, return
  // it to the trigger on close.
  useEffect(() => {
    if (!open) return;
    previousActive.current = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => dialogRef.current?.focus());

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousActive.current?.focus?.();
    };
  }, [open, close]);

  if (!open) return null;

  // Build the dynamic tab list: insert Onboard / Metrics tabs right after
  // Overview when their respective namespace has data. Skipped silently when
  // empty so the modal stays clean on stores that haven't run /memoir-onboard
  // or accumulated any per-branch metrics yet.
  const onboardItems = onboardData?.items ?? [];
  const metricsItems = metricsData?.items ?? [];
  const sections: { key: TabKey; label: string }[] = [];
  for (const s of BASE_SECTIONS) {
    sections.push(s);
    if (s.key === "overview") {
      if (onboardItems.length > 0) {
        sections.push({ key: "onboard", label: "Codebase" });
      }
      if (metricsItems.length > 0) {
        sections.push({ key: "metrics", label: "Metrics" });
      }
    }
  }

  return (
    <div
      className="stats-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className="stats-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stats-title"
        tabIndex={-1}
      >
        <header className="stats-header">
          <div>
            <h2 id="stats-title" className="stats-title">
              Statistics
            </h2>
            {data && (
              <span className="stats-generated">
                Generated {new Date(data.generated_at).toLocaleString()}
              </span>
            )}
          </div>
          <button
            type="button"
            className="stats-close"
            onClick={close}
            aria-label="Close statistics"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <nav className="stats-tabs" role="tablist" aria-label="Statistics sections">
          {sections.map((s) => (
            <button
              key={s.key}
              role="tab"
              aria-selected={tab === s.key}
              className={`stats-tab${tab === s.key ? " active" : ""}`}
              onClick={() => setTab(s.key)}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div className="stats-body">
          {loading && !data && <div className="stats-empty">Loading…</div>}
          {error && <div className="stats-empty stats-error">Failed: {error}</div>}
          {data && tab === "overview" && (
            <OverviewPanel block={data.statistics} storePath={data.store_path} />
          )}
          {tab === "onboard" && <OnboardPanel items={onboardItems} />}
          {tab === "metrics" && <MetricsPanel items={metricsItems} />}
          {data && tab !== "overview" && tab !== "onboard" && tab !== "metrics" && (
            <SectionPanel section={data.statistics[tab]} title={tab} />
          )}
        </div>
      </div>
    </div>
  );
}

function OverviewPanel({
  block,
  storePath,
}: {
  block: StatisticsBlock;
  storePath: string;
}) {
  const cells: { label: string; value: React.ReactNode; tone?: "accent" }[] = [
    {
      label: "Memories",
      value: numericOrDash(block.storage.total_keys),
      tone: "accent",
    },
    {
      label: "Namespaces",
      value: numericOrDash(block.storage.total_namespaces),
    },
    {
      label: "Commits",
      value: numericOrDash(block.versioning.total_commits),
    },
    {
      label: "Branches",
      value: numericOrDash(block.versioning.total_branches),
    },
    {
      label: "Store size",
      value: `${block.storage.store_size_mb ?? "—"} MB`,
    },
    {
      label: "Tree depth",
      value: numericOrDash(block.tree_structure.total_levels),
    },
    {
      label: "Current branch",
      value: <code>{String(block.versioning.current_branch ?? "—")}</code>,
    },
    {
      label: "Last commit",
      value: String(block.versioning.last_commit_message ?? "—"),
    },
  ];

  return (
    <div className="stats-overview">
      <div className="stats-overview-store">
        <span className="eyebrow">Store</span>
        <code>{storePath}</code>
      </div>
      <div className="stats-card-grid">
        {cells.map((c, i) => (
          <div key={i} className={`stats-cell${c.tone ? " " + c.tone : ""}`}>
            <span className="stats-cell-label">{c.label}</span>
            <span className="stats-cell-value">{c.value}</span>
          </div>
        ))}
      </div>

      {hasObject(block.tree_structure.categories) && (
        <BarDistribution
          title="Memories per top-level category"
          dist={block.tree_structure.categories as Record<string, number>}
        />
      )}
    </div>
  );
}

function SectionPanel({ section, title }: { section: StatsSection; title: string }) {
  const entries = Object.entries(section);
  if (entries.length === 0) {
    return (
      <div className="stats-empty">
        No data in <code>{title}</code> yet.
      </div>
    );
  }
  return (
    <div className="stats-section">
      {entries.map(([key, value]) => (
        <StatRow key={key} label={key} value={value} />
      ))}
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: unknown }) {
  if (
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    isFlatNumberRecord(value as Record<string, unknown>)
  ) {
    return (
      <BarDistribution
        title={prettyLabel(label)}
        dist={value as Record<string, number>}
      />
    );
  }

  return (
    <div className="stats-row">
      <span className="stats-row-label">{prettyLabel(label)}</span>
      <span className="stats-row-value">{renderValue(value)}</span>
    </div>
  );
}

function BarDistribution({
  title,
  dist,
}: {
  title: string;
  dist: Record<string, number>;
}) {
  const entries = Object.entries(dist);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <section className="stats-bars">
      <h4 className="stats-bars-title">{title}</h4>
      <ul className="stats-bars-list">
        {entries
          .sort(([, a], [, b]) => b - a)
          .map(([key, value]) => {
            const pct = (value / max) * 100;
            return (
              <li key={key} className="stats-bar-row">
                <code className="stats-bar-label">{key}</code>
                <div className="stats-bar-track" aria-hidden="true">
                  <span
                    className="stats-bar-fill"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="stats-bar-value">{value}</span>
              </li>
            );
          })}
      </ul>
    </section>
  );
}

function OnboardPanel({ items }: { items: OnboardItem[] }) {
  // Mirror render_codebase_onboard_compact in the SessionStart hook: split
  // _meta.* off as a header, then group the rest by L1 prefix and render
  // each child as `<key>: <first-sentence>`. No LLM, no truncation beyond
  // what the writer already enforced (≤500 chars per stored value).
  const meta: Record<string, string> = {};
  const groups: Record<string, OnboardItem[]> = {};
  for (const it of items) {
    if (it.key.startsWith("_meta.")) {
      meta[it.key] = String(it.value ?? "");
      continue;
    }
    const root = it.key.split(".", 1)[0];
    (groups[root] = groups[root] || []).push(it);
  }

  const lastCommit = (meta["_meta.last_onboard.commit"] ?? "").slice(0, 7) || "?";
  const lastDate = meta["_meta.last_onboard.date"] ?? "";
  const mode = meta["_meta.last_onboard.mode"] ?? "?";

  // Preferred ordering matches the SessionStart compact view.
  const PREFERRED = [
    "goal",
    "structure",
    "test",
    "debug",
    "deploy",
    "rules",
    "lessons",
    "references",
    "document",
  ];
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const r of PREFERRED) {
    if (groups[r]) {
      ordered.push(r);
      seen.add(r);
    }
  }
  for (const r of Object.keys(groups).sort()) {
    if (!seen.has(r)) ordered.push(r);
  }

  return (
    <div className="stats-section stats-onboard">
      <div className="stats-row">
        <span className="stats-row-label">Last onboard</span>
        <span className="stats-row-value">
          <code>{lastCommit}</code> · {lastDate || "(no date)"} · {mode}
        </span>
      </div>
      {ordered.map((root) => (
        <section key={root} className="stats-bars">
          <h4 className="stats-bars-title">
            {prettyLabel(root)} <span className="stats-row-empty">({groups[root].length})</span>
          </h4>
          <ul className="stats-bars-list">
            {groups[root]
              .slice()
              .sort((a, b) => a.key.localeCompare(b.key))
              .map((it) => (
                <li key={it.key} className="stats-bar-row">
                  <code className="stats-bar-label" title={it.key}>
                    {it.key}
                  </code>
                  <span className="stats-bar-value">{firstSentence(String(it.value ?? ""))}</span>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function MetricsPanel({ items }: { items: MetricsItem[] }) {
  // Tabular: rows are branches, columns are individual accumulator fields.
  // Column order is fixed and matches the schema written by merge-metrics.py.
  // schema_version / tokens / llms are intentionally omitted — constant or
  // null today, so they'd be visual noise across rows.
  const COLUMNS: { key: string; label: string; derive?: (v: Record<string, unknown>) => unknown }[] = [
    { key: "turns_count", label: "Turns" },
    { key: "total_tool_calls", label: "Calls" },
    { key: "total_tool_errors", label: "Errors" },
    { key: "total_repeated_tool_calls", label: "Repeats" },
    {
      key: "avg_latency_ms",
      label: "Avg latency (ms)",
      derive: (v) => {
        const total = v.total_latency_ms;
        const samples = v.latency_samples;
        if (typeof total === "number" && typeof samples === "number" && samples > 0) {
          return Math.round(total / samples);
        }
        return null;
      },
    },
    { key: "total_output_chars", label: "Output chars" },
    { key: "total_tool_input_chars", label: "Tool input chars" },
    { key: "total_tool_result_chars", label: "Tool result chars" },
  ];

  const rows = items.map((it) => ({
    branch: it.branch ?? it.key,
    value: (it.value && typeof it.value === "object" ? it.value : {}) as Record<string, unknown>,
  }));

  // Build branch→value distributions for the three charts. Filter out
  // branches that don't have a usable number for that specific metric so
  // missing data doesn't render as a zero bar (which would imply the branch
  // had zero latency, not "no samples").
  const avgLatencyDist: Record<string, number> = {};
  const outputCharsDist: Record<string, number> = {};
  const toolResultCharsDist: Record<string, number> = {};
  for (const row of rows) {
    const total = row.value.total_latency_ms;
    const samples = row.value.latency_samples;
    if (typeof total === "number" && typeof samples === "number" && samples > 0) {
      avgLatencyDist[row.branch] = Math.round(total / samples);
    }
    if (typeof row.value.total_output_chars === "number") {
      outputCharsDist[row.branch] = row.value.total_output_chars;
    }
    if (typeof row.value.total_tool_result_chars === "number") {
      toolResultCharsDist[row.branch] = row.value.total_tool_result_chars;
    }
  }

  return (
    <div className="stats-section">
      <div className="stats-metrics-table-wrap">
        <table className="stats-metrics-table">
          <thead>
            <tr>
              <th className="stats-metrics-branch">Branch</th>
              {COLUMNS.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.branch}>
                <td className="stats-metrics-branch">
                  <code>{row.branch}</code>
                </td>
                {COLUMNS.map((c) => {
                  const raw = c.derive ? c.derive(row.value) : row.value[c.key];
                  return (
                    <td key={c.key} className="stats-metrics-num">
                      {typeof raw === "number" ? raw.toLocaleString() : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {Object.keys(avgLatencyDist).length > 0 && (
        <BarDistribution title="Avg latency (ms) per branch" dist={avgLatencyDist} />
      )}
      {Object.keys(outputCharsDist).length > 0 && (
        <BarDistribution title="Output chars per branch" dist={outputCharsDist} />
      )}
      {Object.keys(toolResultCharsDist).length > 0 && (
        <BarDistribution title="Tool result chars per branch" dist={toolResultCharsDist} />
      )}
    </div>
  );
}

function firstSentence(s: string, maxLen = 140): string {
  const trimmed = s.trim().replace(/\s+/g, " ");
  const m = /^(.+?[.!?])(\s|$)/.exec(trimmed);
  let out = m ? m[1] : trimmed;
  if (out.length > maxLen) out = out.slice(0, maxLen - 1).trimEnd() + "…";
  return out;
}

// ---------- helpers ----------

function numericOrDash(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString() : "—";
}

function hasObject(v: unknown): boolean {
  return v != null && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length > 0;
}

function isFlatNumberRecord(o: Record<string, unknown>): boolean {
  return Object.values(o).every((v) => typeof v === "number");
}

function prettyLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function renderValue(v: unknown): React.ReactNode {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return v.toLocaleString();
  if (typeof v === "string") return v;
  if (Array.isArray(v)) {
    if (v.length === 0) return <span className="stats-row-empty">(empty)</span>;
    if (v.every((x) => typeof x === "string" || typeof x === "number")) {
      return v.join(", ");
    }
    return <code className="stats-row-json">{JSON.stringify(v)}</code>;
  }
  if (typeof v === "object") {
    return (
      <code className="stats-row-json">{JSON.stringify(v, null, 2)}</code>
    );
  }
  return String(v);
}
