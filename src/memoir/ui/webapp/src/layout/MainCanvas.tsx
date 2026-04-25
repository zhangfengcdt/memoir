import { useEffect, useState } from "react";
import { useStore } from "../state/storeSlice";
import { dispatch } from "../commands/registry";
import type { HistoryEntry } from "../state/storeSlice";
import "./MainCanvas.css";

type ViewKey = "commits" | "tree" | "graph" | "timeline" | "places";

interface MainCanvasProps {
  onOpenDrawer: () => void;
}

const VIEWS: { key: ViewKey; label: string; shortcut: string }[] = [
  { key: "commits", label: "Commits", shortcut: "⌘1" },
  { key: "tree", label: "Tree", shortcut: "⌘2" },
  { key: "graph", label: "Graph", shortcut: "⌘3" },
  { key: "timeline", label: "Timeline", shortcut: "⌘4" },
  { key: "places", label: "Places", shortcut: "⌘5" },
];

export default function MainCanvas({ onOpenDrawer }: MainCanvasProps) {
  const [active, setActive] = useState<ViewKey>("commits");
  const storePath = useStore((s) => s.storePath);
  const data = useStore((s) => s.data);
  const history = useStore((s) => s.history);
  const status = useStore((s) => s.status);

  // Auto-connect on first mount when the CLI passed ?store=<path>.
  useEffect(() => {
    if (storePath && status === "idle") {
      useStore.getState().connect(storePath);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connected = Boolean(data);

  return (
    <section className="main-canvas">
      <nav className="view-tabs" role="tablist">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            role="tab"
            aria-selected={active === v.key}
            className={`view-tab ${active === v.key ? "active" : ""}`}
            onClick={() => setActive(v.key)}
          >
            <span>{v.label}</span>
            <kbd className="view-tab-kbd">{v.shortcut}</kbd>
          </button>
        ))}
      </nav>

      <div className="view-body">
        {connected ? (
          <ConnectedView view={active} onOpenDrawer={onOpenDrawer} />
        ) : (
          <DisconnectedView />
        )}
        {history.length > 0 && <HistoryLog entries={history} />}
      </div>
    </section>
  );
}

function DisconnectedView() {
  const [path, setPath] = useState("");
  const status = useStore((s) => s.status);
  const onConnect = async () => {
    if (!path.trim()) return;
    await dispatch(`/connect ${path.trim()}`);
  };
  return (
    <div className="empty-state">
      <span className="eyebrow">Get started</span>
      <h2 className="empty-title">No store connected</h2>
      <p className="empty-lead">
        Type a store path below, or run <code>/connect &lt;path&gt;</code> in the command
        bar. If you launched from the CLI with a store, it auto-connects.
      </p>
      <div className="empty-form">
        <input
          className="empty-input"
          placeholder="/path/to/memoir-store"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onConnect();
          }}
          spellCheck={false}
        />
        <button className="btn btn-primary" onClick={onConnect} disabled={!path.trim() || status === "connecting"}>
          Connect
        </button>
      </div>
    </div>
  );
}

function ConnectedView({
  view,
  onOpenDrawer,
}: {
  view: ViewKey;
  onOpenDrawer: () => void;
}) {
  const data = useStore((s) => s.data);
  if (!data) return null;

  // Phase 3/4/6 will replace these with the real Commits/Tree/Graph views.
  // For now, render the raw JSON summary so the connection path is visible.
  return (
    <div className="connected-view">
      <span className="eyebrow">{view}</span>
      <h2 className="connected-title">{data.store_path}</h2>
      <div className="connected-meta">
        <span className="chip accent">branch: {data.current_branch}</span>
        <span className="chip">{data.total_memories} memories</span>
        <span className="chip">{data.commits.length} commits</span>
        <span className="chip">{data.branches.length} branches</span>
      </div>
      <p className="connected-lead">
        The <code>{view}</code> view will render here in the next phase. For now, every
        detail you'd see in a row lands in the side drawer.
      </p>
      <div className="connected-actions">
        <button className="btn btn-secondary btn-sm" onClick={onOpenDrawer}>
          Preview drawer
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => dispatch("/refresh")}
        >
          Refresh
        </button>
      </div>
    </div>
  );
}

function HistoryLog({ entries }: { entries: HistoryEntry[] }) {
  // Show newest at bottom. Slice to last 30 to avoid DOM bloat in long sessions.
  const recent = entries.slice(-30);
  return (
    <div className="history-log" aria-label="Command history">
      <div className="history-log-header">
        <span className="eyebrow">History</span>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => useStore.getState().clearHistory()}
        >
          Clear
        </button>
      </div>
      <ol className="history-list">
        {recent.map((e) => (
          <li key={e.id} className={`history-entry level-${e.level}`}>
            <code className="history-input">{e.input}</code>
            <div className="history-lines">
              {e.lines.map((l, i) => (
                <div key={i}>{l}</div>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
