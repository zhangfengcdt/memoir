import { useEffect, useState } from "react";
import { useStore } from "../state/storeSlice";
import { useUI, VISIBLE_VIEW_KEYS, type ViewKey } from "../state/uiSlice";
import { dispatch } from "../commands/registry";
import CommitList from "../views/commits/CommitList";
import TaxonomyTree from "../views/tree/TaxonomyTree";
import TaxonomyGraph from "../views/graph/TaxonomyGraph";
import TimelineView from "../views/timeline/TimelineView";
import PlacesView from "../views/places/PlacesView";
import ViewToolbar from "./ViewToolbar";
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
  const status = useStore((s) => s.status);

  // Auto-connect on first mount when the CLI passed ?store=<path>.
  useEffect(() => {
    if (storePath && status === "idle") {
      useStore.getState().connect(storePath);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Defaults bias toward the ``default`` namespace, but a freshly-
  // connected store may not have one (e.g., a codebase-only store with
  // ``codebase:onboard`` only). Clear an orphaned filter so the user
  // doesn't hit an empty Tree view with no idea why.
  useEffect(() => {
    if (!data) return;
    const ns = useUI.getState().selectedNamespace;
    if (ns && !(ns in data.namespaces)) {
      useUI.getState().setSelectedNamespace(null);
    }
  }, [data]);

  const connected = Boolean(data);

  return (
    <main className="main-canvas" aria-label="Main content">
      <nav className="view-tabs" role="tablist" aria-label="View tabs">
        {VISIBLE_VIEW_KEYS.map((key) => {
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
        <ViewToolbar />
      </nav>

      <div className="view-body" role="tabpanel" aria-label={`${active} view`}>
        {connected ? (
          <ViewBody view={active} />
        ) : (
          <DisconnectedView />
        )}
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
      return <TaxonomyGraph />;
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

