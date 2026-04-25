import { useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type {
  StatisticsBlock,
  StatisticsResponse,
  StatsSection,
} from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "./StatsModal.css";

type SectionKey = keyof StatisticsBlock;

const SECTIONS: { key: SectionKey | "overview"; label: string }[] = [
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<SectionKey | "overview">("overview");

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  // Fetch when modal opens; abandon when it closes.
  useEffect(() => {
    if (!open || !storePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
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
          {SECTIONS.map((s) => (
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
          {data && tab !== "overview" && (
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
