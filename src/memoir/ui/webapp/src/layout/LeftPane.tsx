import { useStore } from "../state/storeSlice";
import {
  isHiddenNamespace,
  namespaceFilterDisabledReason,
  useUI,
} from "../state/uiSlice";
import type { ViewKey } from "../state/uiSlice";
import "./LeftPane.css";

export default function LeftPane() {
  const data = useStore((s) => s.data);
  const status = useStore((s) => s.status);
  const collapsed = useUI((s) => s.leftCollapsed);
  const activeView = useUI((s) => s.activeView);
  const setActiveView = useUI((s) => s.setActiveView);

  if (collapsed) {
    // Match the visible tab bar — timeline + places are hidden for now
    // and live behind slash commands only.
    const rail: { key: ViewKey; title: string; icon: RailIconKind }[] = [
      { key: "commits", title: "Commits (⌘1)", icon: "commits" },
      { key: "tree", title: "Tree (⌘2)", icon: "tree" },
      { key: "graph", title: "Graph (⌘3)", icon: "graph" },
    ];
    return (
      <aside className="leftpane leftpane-collapsed" aria-label="Navigation rail">
        {rail.map((r) => (
          <button
            key={r.key}
            className={`rail-btn${activeView === r.key ? " active" : ""}`}
            title={r.title}
            onClick={() => setActiveView(r.key)}
            aria-label={r.title}
          >
            <RailIcon kind={r.icon} />
          </button>
        ))}
      </aside>
    );
  }

  return (
    <aside className="leftpane" aria-label="Store navigation">
      <div className="leftpane-section">
        <div className="leftpane-header">
          <span className="eyebrow">Outline</span>
          <span className="leftpane-count">{data?.total_memories ?? 0}</span>
        </div>

        {data ? (
          <NamespaceList namespaces={data.namespaces} />
        ) : status === "connecting" ? (
          <div className="leftpane-placeholder">
            <p>Connecting…</p>
          </div>
        ) : status === "error" ? (
          <div className="leftpane-placeholder leftpane-error">
            <p>Connection failed. Try /connect &lt;path&gt; again.</p>
          </div>
        ) : (
          <div className="leftpane-placeholder">
            <p>Connect to a memory store to see its taxonomy.</p>
            <code className="leftpane-hint">/connect &lt;path&gt;</code>
          </div>
        )}
      </div>
    </aside>
  );
}

function NamespaceList({ namespaces }: { namespaces: Record<string, unknown> }) {
  // ``default`` always pinned to the top (right under "All namespaces"),
  // then everything else alphabetically. Backend insertion order isn't
  // stable, so we explicitly sort. Hidden namespaces (taxonomy-loader
  // bookkeeping, etc.) are dropped — see HIDDEN_NAMESPACE_PREFIXES.
  const entries = Object.entries(namespaces)
    .filter(([ns]) => !isHiddenNamespace(ns))
    .sort(([a], [b]) => {
      if (a === "default") return -1;
      if (b === "default") return 1;
      return a.localeCompare(b);
    });
  const selected = useUI((s) => s.selectedNamespace);
  const setSelected = useUI((s) => s.setSelectedNamespace);
  const activeView = useUI((s) => s.activeView);
  const disabledReason = namespaceFilterDisabledReason(activeView);
  const filterActive = disabledReason === null;

  const totalCount = entries.reduce(
    (sum, [, v]) => sum + (Array.isArray(v) ? v.length : countLeaves(v)),
    0,
  );

  if (entries.length === 0) {
    return (
      <div className="leftpane-placeholder">
        <p>No namespaces yet. Run /remember to start capturing.</p>
      </div>
    );
  }
  return (
    <>
      {!filterActive && (
        <p className="namespace-disabled-note" title={disabledReason ?? undefined}>
          {disabledReason}
        </p>
      )}
      <ul
        className={`namespace-list${filterActive ? "" : " namespace-list-muted"}`}
        role="listbox"
        aria-label="Namespaces filter"
      >
        <li>
          <button
            type="button"
            role="option"
            aria-selected={selected === null}
            className={`namespace-item${selected === null ? " selected" : ""}`}
            onClick={() => setSelected(null)}
            title={
              filterActive
                ? "Show data from all namespaces"
                : (disabledReason ?? "")
            }
          >
            <span className="namespace-name">All namespaces</span>
            <span className="namespace-count">{totalCount}</span>
          </button>
        </li>
        {entries.map(([ns, value]) => {
          const count = Array.isArray(value) ? value.length : countLeaves(value);
          const isSelected = selected === ns;
          return (
            <li key={ns}>
              <button
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`namespace-item${isSelected ? " selected" : ""}`}
                onClick={() => setSelected(isSelected ? null : ns)}
                title={
                  filterActive
                    ? isSelected
                      ? `Click again to clear; currently filtering to ${ns}`
                      : `Filter views to ${ns}`
                    : (disabledReason ?? "")
                }
              >
                <span className="namespace-name">{ns}</span>
                <span className="namespace-count">{count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function countLeaves(node: unknown): number {
  if (node == null) return 0;
  if (Array.isArray(node)) return node.length;
  if (typeof node === "object") {
    return Object.values(node as Record<string, unknown>).reduce<number>(
      (sum, v) => sum + countLeaves(v),
      0,
    );
  }
  return 1;
}

type RailIconKind = "commits" | "tree" | "graph" | "timeline";

function RailIcon({ kind }: { kind: RailIconKind }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  switch (kind) {
    case "commits":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="4" />
          <line x1="12" y1="2" x2="12" y2="8" />
          <line x1="12" y1="16" x2="12" y2="22" />
        </svg>
      );
    case "tree":
      return (
        <svg {...common}>
          <path d="M3 5h4v4H3zM3 15h4v4H3zM13 5h8M13 10h8M13 15h8M13 20h8" />
        </svg>
      );
    case "graph":
      return (
        <svg {...common}>
          <circle cx="5" cy="6" r="2" />
          <circle cx="19" cy="6" r="2" />
          <circle cx="12" cy="18" r="2" />
          <line x1="5" y1="6" x2="19" y2="6" />
          <line x1="5" y1="6" x2="12" y2="18" />
          <line x1="19" y1="6" x2="12" y2="18" />
        </svg>
      );
    case "timeline":
      return (
        <svg {...common}>
          <line x1="3" y1="12" x2="21" y2="12" />
          <circle cx="7" cy="12" r="2" />
          <circle cx="14" cy="12" r="2" />
        </svg>
      );
  }
}
