import { useState } from "react";
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
        <EmptyView view={active} onOpenDrawer={onOpenDrawer} />
      </div>
    </section>
  );
}

function EmptyView({ view, onOpenDrawer }: { view: ViewKey; onOpenDrawer: () => void }) {
  return (
    <div className="empty-state">
      <span className="eyebrow">{view}</span>
      <h2 className="empty-title">No store connected</h2>
      <p className="empty-lead">
        Connect to a memoir store to load commits, taxonomy, and graph data.
      </p>
      <div className="empty-actions">
        <button className="btn btn-primary">Connect store</button>
        <button className="btn btn-secondary" onClick={onOpenDrawer}>
          Preview drawer
        </button>
      </div>
    </div>
  );
}
