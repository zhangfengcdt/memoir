import type { Commit } from "../api/types";
import { absoluteTime, relativeTime } from "../lib/time";
import "./DrawerPanels.css";

interface CommitDetailProps {
  commit: Commit;
}

export default function CommitDetail({ commit }: CommitDetailProps) {
  return (
    <div className="drawer-panel commit-detail">
      <header className="drawer-panel-header">
        <span className="eyebrow">Commit</span>
        <h3 className="drawer-panel-title">
          <code>{commit.short_hash}</code>
        </h3>
        <div className="drawer-panel-meta">
          {commit.refs.map((ref) => (
            <span key={`ref-${ref}`} className="chip accent">
              {ref}
            </span>
          ))}
          {commit.tags.map((tag) => (
            <span key={`tag-${tag}`} className="chip tag">
              {tag}
            </span>
          ))}
        </div>
      </header>

      <section className="drawer-panel-section">
        <span className="eyebrow">Message</span>
        <p className="commit-message-full">{commit.message}</p>
      </section>

      <section className="drawer-panel-section">
        <span className="eyebrow">Author</span>
        <div className="drawer-kv-grid">
          <span>Name</span>
          <span>{commit.author}</span>
          <span>Email</span>
          <code>{commit.email}</code>
          <span>When</span>
          <span>
            {relativeTime(commit.timestamp)}
            <span className="commit-exact-time"> — {absoluteTime(commit.timestamp)}</span>
          </span>
        </div>
      </section>

      <section className="drawer-panel-section">
        <span className="eyebrow">Full hash</span>
        <code className="commit-full-hash">{commit.hash}</code>
      </section>

      <section className="drawer-panel-section">
        <span className="eyebrow">Operations</span>
        <div className="drawer-panel-actions">
          <button
            className="btn btn-secondary btn-sm"
            title="Phase 6 — not wired yet"
            disabled
          >
            Show changes
          </button>
          <button
            className="btn btn-secondary btn-sm"
            title="Phase 6 — not wired yet"
            disabled
          >
            Check out
          </button>
        </div>
      </section>
    </div>
  );
}
