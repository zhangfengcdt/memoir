import { useStore } from "../state/storeSlice";
import "./LeftPane.css";

interface LeftPaneProps {
  collapsed: boolean;
}

export default function LeftPane({ collapsed }: LeftPaneProps) {
  const data = useStore((s) => s.data);
  const status = useStore((s) => s.status);

  if (collapsed) {
    return (
      <aside className="leftpane leftpane-collapsed" aria-label="Navigation rail">
        <button className="rail-btn active" title="Commits">
          <RailIcon kind="commits" />
        </button>
        <button className="rail-btn" title="Tree">
          <RailIcon kind="tree" />
        </button>
        <button className="rail-btn" title="Graph">
          <RailIcon kind="graph" />
        </button>
        <button className="rail-btn" title="Timeline">
          <RailIcon kind="timeline" />
        </button>
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
  const entries = Object.entries(namespaces);
  if (entries.length === 0) {
    return (
      <div className="leftpane-placeholder">
        <p>No namespaces yet. Run /remember to start capturing.</p>
      </div>
    );
  }
  return (
    <ul className="namespace-list">
      {entries.map(([ns, value]) => {
        const count = Array.isArray(value) ? value.length : countLeaves(value);
        return (
          <li key={ns} className="namespace-item">
            <span className="namespace-name">{ns}</span>
            <span className="namespace-count">{count}</span>
          </li>
        );
      })}
    </ul>
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

function RailIcon({ kind }: { kind: "commits" | "tree" | "graph" | "timeline" }) {
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
