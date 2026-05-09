import { useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type {
  MetricsItem,
  MetricsResponse,
  OnboardItem,
  OnboardResponse,
  ProjectOnboardItem,
  ProjectOnboardResponse,
  StatisticsBlock,
  StatisticsResponse,
  StatsSection,
} from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "./StatsModal.css";

type SectionKey = keyof StatisticsBlock;
type TabKey =
  | SectionKey
  | "overview"
  | "onboard"
  | "project"
  | "metrics"
  | "codechanges";

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
  // Current branch from the store (`/api/store` response). Used to filter
  // metrics.code.<branch> entries so the Code Changes tab matches the
  // active branch the same way metrics.turn.<branch> does on the server.
  const currentBranch = useStore((s) => s.data?.current_branch ?? null);

  const [data, setData] = useState<StatisticsResponse | null>(null);
  const [onboardData, setOnboardData] = useState<OnboardResponse | null>(null);
  const [projectOnboardData, setProjectOnboardData] =
    useState<ProjectOnboardResponse | null>(null);
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
    setProjectOnboardData(null);
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
      .projectOnboard(storePath)
      .then((res) => {
        if (!cancelled) setProjectOnboardData(res);
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

  // Build the dynamic tab list: insert Codebase / Project / Metrics tabs right
  // after Overview when their respective namespace has data. Skipped silently
  // when empty so the modal stays clean on stores that haven't run
  // /memoir-onboard or accumulated any per-branch metrics yet. Codebase and
  // Project are mutually exclusive in normal use (a store is either git-mode
  // or non-git-mode for the project), but the UI doesn't enforce that — both
  // tabs can appear if both namespaces happen to be populated.
  const onboardItems = onboardData?.items ?? [];
  const projectOnboardItems = projectOnboardData?.items ?? [];
  const metricsItems = metricsData?.items ?? [];
  // Aggregate metrics.code.* across every branch into one timeline. Each
  // entry keeps its source branch so the UI can label it; rows are sorted
  // newest-first regardless of which branch produced them. Tab hides when
  // there are no entries at all.
  const codeMetricsEntries = collectCodeMetricsEntries(metricsItems);
  // Metrics tab is turn-only; code metrics power Code Changes. Hide the
  // Metrics tab if there are no turn rows to show, otherwise the table
  // would render empty when only metrics.code.* items exist.
  const turnMetricsItems = metricsItems.filter((it) =>
    it.key.startsWith("metrics.turn."),
  );
  const sections: { key: TabKey; label: string }[] = [];
  for (const s of BASE_SECTIONS) {
    sections.push(s);
    if (s.key === "overview") {
      if (onboardItems.length > 0) {
        sections.push({ key: "onboard", label: "Codebase" });
      }
      if (projectOnboardItems.length > 0) {
        sections.push({ key: "project", label: "Project" });
      }
      if (turnMetricsItems.length > 0) {
        sections.push({ key: "metrics", label: "Metrics" });
      }
      if (codeMetricsEntries.length > 0) {
        sections.push({ key: "codechanges", label: "Code Changes" });
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
          {tab === "onboard" && (
            <OnboardPanel
              items={onboardItems}
              currentCodeCommit={onboardData?.current_code_commit ?? null}
              currentCodeBranch={onboardData?.current_code_branch ?? null}
            />
          )}
          {tab === "project" && <ProjectOnboardPanel items={projectOnboardItems} />}
          {tab === "metrics" && <MetricsPanel items={metricsItems} />}
          {tab === "codechanges" && (
            <CodeChangesPanel
              entries={codeMetricsEntries}
              currentBranch={currentBranch}
            />
          )}
          {data &&
            tab !== "overview" &&
            tab !== "onboard" &&
            tab !== "project" &&
            tab !== "metrics" &&
            tab !== "codechanges" && (
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
  tone,
}: {
  title: string;
  dist: Record<string, number>;
  /** Color variant. Default uses --accent (green). "warning" uses --warning. */
  tone?: "warning";
}) {
  const entries = Object.entries(dist);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <section className={`stats-bars${tone ? ` tone-${tone}` : ""}`}>
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

function OnboardPanel({
  items,
  currentCodeCommit,
  currentCodeBranch,
}: {
  items: OnboardItem[];
  currentCodeCommit: string | null;
  currentCodeBranch: string | null;
}) {
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

  const fullSnapshotCommit = meta["_meta.last_onboard.commit"] ?? "";
  const lastCommit = fullSnapshotCommit.slice(0, 7) || "?";
  const lastDate = meta["_meta.last_onboard.date"] ?? "";
  const mode = meta["_meta.last_onboard.mode"] ?? "?";

  // "Out of sync" when we know both commits and they differ. We compare on
  // the full SHAs (not the 7-char displayed prefix) to avoid false positives
  // from the rare prefix collision.
  const outOfSync =
    fullSnapshotCommit && currentCodeCommit && fullSnapshotCommit !== currentCodeCommit;
  const currentShort = currentCodeCommit ? currentCodeCommit.slice(0, 7) : "";

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
          {outOfSync && (
            <span
              className="stats-onboard-stale"
              title={`Code repo is at ${currentCodeCommit}${
                currentCodeBranch ? ` on ${currentCodeBranch}` : ""
              } — run /memoir-onboard to refresh the snapshot.`}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>
                out of sync — code is at <code>{currentShort}</code>
                {currentCodeBranch && (
                  <>
                    {" on "}
                    <code>{currentCodeBranch}</code>
                  </>
                )}
              </span>
            </span>
          )}
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

function ProjectOnboardPanel({ items }: { items: ProjectOnboardItem[] }) {
  // Mirror render_project_onboard_compact (the bash/Python version in
  // hooks/common.sh) but rendered as React: split _meta.* off as a header,
  // suppress the files.* root (hundreds of per-file keys would explode the
  // body — we surface the aggregate file_count instead), then group the rest
  // by L1 prefix. Identity field is snapshot_hash, not a code SHA, since
  // non-git folders have no code commit to anchor to.
  const meta: Record<string, string> = {};
  const groups: Record<string, ProjectOnboardItem[]> = {};
  for (const it of items) {
    if (it.key.startsWith("_meta.")) {
      meta[it.key] = String(it.value ?? "");
      continue;
    }
    const root = it.key.split(".", 1)[0];
    // Suppress files.* — too many keys to render usefully here. The aggregate
    // count surfaces in the header row from _meta.last_onboard.file_count.
    if (root === "files") continue;
    (groups[root] = groups[root] || []).push(it);
  }

  const fullSnapshotHash = meta["_meta.last_onboard.snapshot_hash"] ?? "";
  const lastHash = fullSnapshotHash.slice(0, 7) || "?";
  const lastDate = meta["_meta.last_onboard.date"] ?? "";
  const mode = meta["_meta.last_onboard.mode"] ?? "?";
  const fileCount = meta["_meta.last_onboard.file_count"] ?? "";

  // Stale signal: > 30 days since last onboard. project:onboard has no code
  // SHA to compare against, so age is the only out-of-date hint we render.
  const stale = (() => {
    if (!lastDate) return false;
    const t = Date.parse(lastDate);
    if (Number.isNaN(t)) return false;
    const ageMs = Date.now() - t;
    return ageMs > 30 * 24 * 60 * 60 * 1000;
  })();

  // Preferred ordering matches the SessionStart project:onboard compact view.
  const PREFERRED = ["summary", "structure"];
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

  // structure.tree is multi-line ASCII art — render it in a <pre> instead of
  // first-sentence-truncated like the rest, so the user sees the actual tree.
  const treeKey = "structure.tree";
  const treeItem = items.find((it) => it.key === treeKey);
  const treeText = treeItem ? String(treeItem.value ?? "") : "";

  return (
    <div className="stats-section stats-onboard">
      <div className="stats-row">
        <span className="stats-row-label">Last onboard</span>
        <span className="stats-row-value">
          <code>{lastHash}</code> · {lastDate || "(no date)"} · {mode}
          {stale && (
            <span
              className="stats-onboard-stale"
              title="Snapshot is more than 30 days old — run /memoir-onboard to refresh."
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>stale — run /memoir-onboard to refresh</span>
            </span>
          )}
        </span>
      </div>
      {fileCount && (
        <div className="stats-row">
          <span className="stats-row-label">Files indexed</span>
          <span className="stats-row-value">{fileCount}</span>
        </div>
      )}
      {ordered.map((root) => (
        <section key={root} className="stats-bars">
          <h4 className="stats-bars-title">
            {prettyLabel(root)}{" "}
            <span className="stats-row-empty">({groups[root].length})</span>
          </h4>
          <ul className="stats-bars-list">
            {groups[root]
              .slice()
              .sort((a, b) => a.key.localeCompare(b.key))
              .filter((it) => it.key !== treeKey)
              .map((it) => (
                <li key={it.key} className="stats-bar-row">
                  <code className="stats-bar-label" title={it.key}>
                    {it.key}
                  </code>
                  <span className="stats-bar-value">
                    {firstSentence(String(it.value ?? ""))}
                  </span>
                </li>
              ))}
          </ul>
        </section>
      ))}
      {treeText && (
        <section className="stats-bars">
          <h4 className="stats-bars-title">{treeKey}</h4>
          <pre className="stats-onboard-tree">{treeText}</pre>
        </section>
      )}
    </div>
  );
}

// One row of the Code Changes timeline. `branch` is the originating
// branch (the suffix of the metrics.code.<branch> key); we keep it on the
// row so the panel can label rows when aggregating across branches.
type CodeChangeEntry = { timestamp: number; summary: string; branch: string };

// Collect every entry from every metrics.code.<branch> item across the
// store, tagging each row with its source branch and sorting newest-first.
// Returns [] when there are no metrics.code.* items at all, which causes
// the Code Changes tab to be hidden entirely.
function collectCodeMetricsEntries(items: MetricsItem[]): CodeChangeEntry[] {
  const out: CodeChangeEntry[] = [];
  for (const item of items) {
    if (!item.key.startsWith("metrics.code.")) continue;
    const branch = item.branch ?? "unknown";
    if (typeof item.value !== "object" || item.value === null) continue;
    const v = item.value as Record<string, unknown>;
    const entries = v.entries;
    if (!Array.isArray(entries)) continue;
    for (const e of entries) {
      if (e && typeof e === "object") {
        const ts = (e as Record<string, unknown>).timestamp;
        const summary = (e as Record<string, unknown>).summary;
        if (typeof ts === "number" && typeof summary === "string") {
          out.push({ timestamp: ts, summary, branch });
        }
      }
    }
  }
  out.sort((a, b) => b.timestamp - a.timestamp);
  return out;
}

// Format an epoch-seconds timestamp as a short relative string ("3m", "2h",
// "yesterday", "Apr 12"). Mirrors lib/time.relativeTimeFromISO but skips the
// ISO parse since the metric stores raw epoch seconds.
function formatCodeChangeTime(epochSeconds: number): string {
  const now = Date.now() / 1000;
  const delta = Math.max(0, now - epochSeconds);
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  if (delta < 7 * 86400) return `${Math.floor(delta / 86400)}d ago`;
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function CodeChangesPanel({
  entries,
  currentBranch,
}: {
  entries: CodeChangeEntry[];
  currentBranch: string | null;
}) {
  // Group entries by branch. Within each group rows are already newest-
  // first because the upstream collector sorted by timestamp. Across
  // groups we order branches by their most-recent timestamp; the user's
  // current branch is pinned first so the most-likely-relevant group
  // is always at the top.
  const groups = new Map<string, CodeChangeEntry[]>();
  for (const e of entries) {
    const list = groups.get(e.branch);
    if (list) list.push(e);
    else groups.set(e.branch, [e]);
  }
  const orderedBranches = Array.from(groups.keys()).sort((a, b) => {
    if (a === currentBranch && b !== currentBranch) return -1;
    if (b === currentBranch && a !== currentBranch) return 1;
    const aMax = groups.get(a)?.[0]?.timestamp ?? 0;
    const bMax = groups.get(b)?.[0]?.timestamp ?? 0;
    return bMax - aMax;
  });

  // Each group is independently collapsible. Default: current branch
  // expanded, every other group collapsed — gives an immediate view of
  // active work without overwhelming the modal when many branches have
  // history.
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(currentBranch && groups.has(currentBranch) ? [currentBranch] : []),
  );
  const toggle = (branch: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(branch)) next.delete(branch);
      else next.add(branch);
      return next;
    });
  };

  // Per-group "Copy as bullets" → PR-description-ready markdown. Tracks
  // which group's button was just clicked so the icon can flash a brief
  // "✓" without standing up a per-row state slot.
  const [copiedBranch, setCopiedBranch] = useState<string | null>(null);
  const copyGroup = async (branch: string, items: CodeChangeEntry[]) => {
    const text = items.map((e) => `- ${e.summary}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopiedBranch(branch);
      setTimeout(() => setCopiedBranch((v) => (v === branch ? null : v)), 1500);
    } catch {
      /* clipboard unavailable — silently no-op */
    }
  };

  return (
    <div className="stats-codechanges">
      <div className="stats-codechanges-header">
        <span className="stats-codechanges-summary">
          All branches{" "}
          <span className="stats-codechanges-divider">·</span>{" "}
          {groups.size} {groups.size === 1 ? "branch" : "branches"}{" "}
          <span className="stats-codechanges-divider">·</span>{" "}
          {entries.length} {entries.length === 1 ? "entry" : "entries"}
        </span>
      </div>
      <div className="stats-codegroups">
        {orderedBranches.map((branch) => {
          const items = groups.get(branch) ?? [];
          const isCurrent = branch === currentBranch;
          const isOpen = expanded.has(branch);
          return (
            <section
              key={branch}
              className={`stats-codegroup${isCurrent ? " is-current" : ""}`}
            >
              {/* Header row: a flex container with the toggle as a left-side
                  button and the copy action as a sibling button on the right.
                  Two siblings rather than nested buttons (illegal HTML) so
                  each control gets its own focus / keyboard semantics. */}
              <div className="stats-codegroup-header-row">
                <button
                  type="button"
                  className="stats-codegroup-header"
                  onClick={() => toggle(branch)}
                  aria-expanded={isOpen}
                  aria-controls={`codegroup-${branch}`}
                >
                  <span
                    className={`stats-codegroup-caret${isOpen ? " is-open" : ""}`}
                    aria-hidden="true"
                  >
                    ▶
                  </span>
                  <code
                    className={`stats-codelog-branch${isCurrent ? " is-current" : ""}`}
                    title={isCurrent ? `${branch} (current)` : branch}
                  >
                    {branch}
                  </code>
                  {isCurrent && (
                    <span className="stats-codegroup-tag">current</span>
                  )}
                  <span className="stats-codegroup-count">
                    {items.length} {items.length === 1 ? "entry" : "entries"}
                  </span>
                </button>
                <button
                  type="button"
                  className="stats-codegroup-copy"
                  onClick={() => copyGroup(branch, items)}
                  aria-label={`Copy ${branch} entries as bullets`}
                  title="Copy entries as a bullet list (PR-ready)"
                >
                  {copiedBranch === branch ? (
                    "✓"
                  ) : (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  )}
                </button>
              </div>
              {isOpen && (
                <ol id={`codegroup-${branch}`} className="stats-codelog">
                  {items.map((entry, i) => (
                    <li key={i} className="stats-codelog-row">
                      <span
                        className="stats-codelog-time"
                        title={new Date(entry.timestamp * 1000).toLocaleString()}
                      >
                        {formatCodeChangeTime(entry.timestamp)}
                      </span>
                      <span className="stats-codelog-summary">
                        {entry.summary}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          );
        })}
      </div>
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
      key: "avg_latency_s",
      label: "Avg latency (s)",
      derive: (v) => {
        const total = v.total_latency_ms;
        const samples = v.latency_samples;
        if (typeof total === "number" && typeof samples === "number" && samples > 0) {
          // ms → seconds, 1 decimal place
          return Math.round(total / samples / 100) / 10;
        }
        return null;
      },
    },
    { key: "total_output_chars", label: "Output chars" },
    { key: "total_tool_input_chars", label: "Tool input chars" },
    { key: "total_tool_result_chars", label: "Tool result chars" },
  ];

  // Only turn metrics belong in this table — `metrics.code.*` items live
  // under a different schema (changes timeline) and are surfaced on the
  // Code Changes tab. Mixing them in here produced duplicate rows per
  // branch with every column dashed out.
  const turnItems = items.filter((it) => it.key.startsWith("metrics.turn."));
  const rows = turnItems.map((it) => ({
    branch: it.branch ?? it.key,
    value: (it.value && typeof it.value === "object" ? it.value : {}) as Record<string, unknown>,
  }));

  // Build branch→value distributions for each chart. Filter out branches
  // that don't have a usable number for that specific metric so missing
  // data doesn't render as a zero bar (which would imply zero, not "no
  // samples"). The tool-errors chart is the exception: zero is meaningful
  // (a clean branch) so we always include it when the field is present.
  const avgLatencyDist: Record<string, number> = {};
  const outputCharsDist: Record<string, number> = {};
  const toolResultCharsDist: Record<string, number> = {};
  const toolErrorsDist: Record<string, number> = {};
  for (const row of rows) {
    const total = row.value.total_latency_ms;
    const samples = row.value.latency_samples;
    if (typeof total === "number" && typeof samples === "number" && samples > 0) {
      // ms → seconds, 1 decimal place
      avgLatencyDist[row.branch] = Math.round(total / samples / 100) / 10;
    }
    if (typeof row.value.total_output_chars === "number") {
      outputCharsDist[row.branch] = row.value.total_output_chars;
    }
    if (typeof row.value.total_tool_result_chars === "number") {
      toolResultCharsDist[row.branch] = row.value.total_tool_result_chars;
    }
    if (typeof row.value.total_tool_errors === "number") {
      toolErrorsDist[row.branch] = row.value.total_tool_errors;
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
        <BarDistribution title="Avg latency (s) per branch" dist={avgLatencyDist} />
      )}
      {Object.keys(toolErrorsDist).length > 0 && (
        <BarDistribution
          title="Tool errors per branch"
          dist={toolErrorsDist}
          tone="warning"
        />
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
