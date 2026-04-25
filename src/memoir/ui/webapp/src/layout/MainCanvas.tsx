import { useEffect, useState } from "react";
import { useStore } from "../state/storeSlice";
import { useUI, VIEW_KEYS, type ViewKey } from "../state/uiSlice";
import { dispatch } from "../commands/registry";
import CommitList from "../views/commits/CommitList";
import TaxonomyTree from "../views/tree/TaxonomyTree";
import CommitGraph from "../views/graph/CommitGraph";
import TimelineView from "../views/timeline/TimelineView";
import PlacesView from "../views/places/PlacesView";
import type { HistoryEntry } from "../state/storeSlice";
import "./MainCanvas.css";

const VIEW_LABELS: Record<ViewKey, { label: string; shortcut: string }> = {
  commits: { label: "Commits", shortcut: "⌘1" },
  tree: { label: "Tree", shortcut: "⌘2" },
  graph: { label: "Graph", shortcut: "⌘3" },
  timeline: { label: "Timeline", shortcut: "⌘4" },
  places: { label: "Places", shortcut: "⌘5" },
};

export default function MainCanvas() {
  const active = useUI((s) => s.activeView);
  const setActive = useUI((s) => s.setActiveView);
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
    <main className="main-canvas" aria-label="Main content">
      <nav className="view-tabs" role="tablist" aria-label="View tabs">
        {VIEW_KEYS.map((key) => {
          const meta = VIEW_LABELS[key];
          return (
            <button
              key={key}
              role="tab"
              aria-selected={active === key}
              className={`view-tab ${active === key ? "active" : ""}`}
              onClick={() => setActive(key)}
            >
              <span>{meta.label}</span>
              <kbd className="view-tab-kbd">{meta.shortcut}</kbd>
            </button>
          );
        })}
      </nav>

      <div className="view-body" role="tabpanel" aria-label={`${active} view`}>
        {connected ? (
          <ViewBody view={active} />
        ) : (
          <DisconnectedView />
        )}
        {history.length > 0 && <HistoryLog entries={history} />}
      </div>
    </main>
  );
}

function ViewBody({ view }: { view: ViewKey }) {
  switch (view) {
    case "commits":
      return <CommitList />;
    case "tree":
      return <TaxonomyTree />;
    case "graph":
      return <CommitGraph />;
    case "timeline":
      return <TimelineView />;
    case "places":
      return <PlacesView />;
  }
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
        <button
          className="btn btn-primary"
          onClick={onConnect}
          disabled={!path.trim() || status === "connecting"}
        >
          Connect
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
