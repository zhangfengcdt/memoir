import type { Memory } from "../api/types";
import "./DrawerPanels.css";

interface MemoryDetailProps {
  memory: Memory;
}

export default function MemoryDetail({ memory }: MemoryDetailProps) {
  const raw = JSON.stringify(memory.value, null, 2);
  const lines = (memory.content ?? "").split("\n");

  return (
    <div className="drawer-panel memory-detail">
      <header className="drawer-panel-header">
        <span className="eyebrow">Memory</span>
        <h3 className="drawer-panel-title">
          <code>{memory.path}</code>
        </h3>
        <div className="drawer-panel-meta">
          <span className="chip accent">{memory.namespace}</span>
          <code className="drawer-panel-key" title={memory.key}>
            {memory.key}
          </code>
        </div>
      </header>

      <section className="drawer-panel-section">
        <span className="eyebrow">Content</span>
        {memory.content ? (
          <div className="drawer-body-content">
            {lines.map((line, i) => (
              <p key={i} className="content-line">
                {line || " "}
              </p>
            ))}
          </div>
        ) : (
          <p className="drawer-empty-hint">(no textual content on this memory)</p>
        )}
      </section>

      <section className="drawer-panel-section">
        <span className="eyebrow">Raw value</span>
        <pre className="drawer-json">
          <code>{raw}</code>
        </pre>
      </section>

      <section className="drawer-panel-section">
        <span className="eyebrow">Operations</span>
        <div className="drawer-panel-actions">
          <button
            className="btn btn-secondary btn-sm"
            title="Phase 6 — not wired yet"
            disabled
          >
            Show proof
          </button>
          <button
            className="btn btn-secondary btn-sm"
            title="Phase 6 — not wired yet"
            disabled
          >
            Show blame
          </button>
        </div>
      </section>
    </div>
  );
}
