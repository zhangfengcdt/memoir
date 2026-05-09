import { Fragment, useEffect, useState } from "react";
import { useStore } from "../state/storeSlice";
import { useUI, VISIBLE_VIEW_KEYS, type ViewKey } from "../state/uiSlice";
import { dispatch } from "../commands/registry";
import CommitList from "../views/commits/CommitList";
import TaxonomyTree from "../views/tree/TaxonomyTree";
import TaxonomyGraph from "../views/graph/TaxonomyGraph";
import TimelineView from "../views/timeline/TimelineView";
import PlacesView from "../views/places/PlacesView";
import ViewToolbar from "./ViewToolbar";
import FilterBar from "./FilterBar";
import "./MainCanvas.css";

const VIEW_LABELS: Record<ViewKey, { label: string; shortcut: string }> = {
  commits: { label: "Commits", shortcut: "⌘1" },
  tree: { label: "Outline", shortcut: "⌘2" },
  graph: { label: "Map", shortcut: "⌘3" },
  timeline: { label: "Timeline", shortcut: "⌘4" },
  places: { label: "Places", shortcut: "⌘5" },
};

// Octicon-style inline icons. Sized via currentColor so they inherit tab color.
const VIEW_ICONS: Record<ViewKey, JSX.Element> = {
  commits: (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path
        fill="currentColor"
        d="M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z"
      />
    </svg>
  ),
  tree: (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path
        fill="currentColor"
        d="M2 4a1 1 0 1 1 0-2 1 1 0 0 1 0 2Zm3.75-1.5a.75.75 0 0 0 0 1.5h9.5a.75.75 0 0 0 0-1.5h-9.5Zm0 5a.75.75 0 0 0 0 1.5h9.5a.75.75 0 0 0 0-1.5h-9.5Zm0 5a.75.75 0 0 0 0 1.5h9.5a.75.75 0 0 0 0-1.5h-9.5ZM2 9a1 1 0 1 1 0-2 1 1 0 0 1 0 2Zm1 4a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"
      />
    </svg>
  ),
  graph: (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path
        fill="currentColor"
        d="M5 3.25a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Zm0 9.5a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0ZM2.5 9.25a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Zm9-1.5a.75.75 0 1 1 1.5 0 .75.75 0 0 1-1.5 0Z"
      />
      <path
        fill="currentColor"
        d="M5.75 2a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5ZM3.25 8a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5ZM12.25 6.5a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5ZM5.75 11a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5Zm.93-7.86 4.79 3.99-.96 1.15-4.79-3.99.96-1.15Zm.07 9.49 4.5-3.75.96 1.15-4.5 3.75-.96-1.15ZM4.21 9.86l3.5 1.5-.59 1.38-3.5-1.5.59-1.38Z"
      />
    </svg>
  ),
  timeline: <></>,
  places: <></>,
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
          const count = tabCount(key, data);
          return (
            <Fragment key={key}>
              <button
                role="tab"
                aria-selected={active === key}
                className={`view-tab ${active === key ? "active" : ""}`}
                onClick={() => setActive(key)}
                title={`${meta.label} (${meta.shortcut})`}
              >
                <span className="view-tab-icon">{VIEW_ICONS[key]}</span>
                <span className="view-tab-label">{meta.label}</span>
                {count !== null && <span className="view-tab-count">{count}</span>}
              </button>
              {key === "graph" && <ViewToolbar />}
            </Fragment>
          );
        })}
      </nav>

      {connected && (active === "tree" || active === "graph") && <FilterBar />}

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

function tabCount(
  key: ViewKey,
  data: ReturnType<typeof useStore.getState>["data"],
): number | null {
  if (!data) return null;
  switch (key) {
    case "commits":
      return data.commits.length;
    case "tree":
    case "graph":
      return data.total_memories;
    default:
      return null;
  }
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

