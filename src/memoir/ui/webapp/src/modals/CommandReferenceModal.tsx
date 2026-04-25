import { useEffect, useMemo, useRef, useState } from "react";
import {
  categoryLabel,
  listCommands,
  tagLabel,
  type CommandCategory,
  type CommandDef,
  type CommandTag,
} from "../commands/registry";
import { useUI } from "../state/uiSlice";
import "./CommandReferenceModal.css";

export default function CommandReferenceModal() {
  const open = useUI((s) => s.helpOpen);
  const close = useUI((s) => s.closeHelp);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);
  const [filter, setFilter] = useState("");

  const grouped = useMemo(() => {
    const allCommands = listCommands();
    const matches = (def: CommandDef) => {
      if (!filter.trim()) return true;
      const needle = filter.trim().toLowerCase().replace(/^\//, "");
      return (
        def.name.includes(needle) ||
        def.aliases.some((a) => a.includes(needle)) ||
        def.summary.toLowerCase().includes(needle) ||
        (def.longDescription?.toLowerCase().includes(needle) ?? false)
      );
    };
    const filtered = allCommands.filter(matches);
    const byCategory = new Map<CommandCategory, CommandDef[]>();
    for (const def of filtered) {
      const list = byCategory.get(def.category) ?? [];
      list.push(def);
      byCategory.set(def.category, list);
    }
    return byCategory;
  }, [filter]);

  useEffect(() => {
    if (!open) return;
    previousActive.current = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => dialogRef.current?.focus());
    setFilter("");

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
      className="cmdref-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className="cmdref-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cmdref-title"
        tabIndex={-1}
      >
        <header className="cmdref-header">
          <div>
            <h2 id="cmdref-title" className="cmdref-title">
              Memoir — Command Reference
            </h2>
            <p className="cmdref-subtitle">
              Type a command in the input or click an entry to copy its usage.
            </p>
          </div>
          <button
            type="button"
            className="cmdref-close"
            onClick={close}
            aria-label="Close command reference"
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

        <section className="cmdref-intro">
          <h3>
            <span className="cmdref-emoji" aria-hidden="true">
              💡
            </span>
            Getting started
          </h3>
          <p>
            Memoir brings Git-like version control to AI memory systems. Connect
            to a memory store to start exploring your data with cryptographic
            integrity and full history tracking.
          </p>
          <p>
            <strong>Quick start:</strong> Use{" "}
            <code>/connect /path/to/store</code> to begin. Auto-complete picks up
            commands as you type.
          </p>
        </section>

        <div className="cmdref-search">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Filter commands…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            spellCheck={false}
            autoCapitalize="off"
            autoComplete="off"
            aria-label="Filter command list"
          />
        </div>

        <div className="cmdref-body">
          {Array.from(grouped.entries()).map(([category, defs]) => (
            <section key={category} className="cmdref-group">
              <div className="cmdref-group-header">
                <span className="cmdref-group-rule" aria-hidden="true" />
                <h3 className="cmdref-group-title">{categoryLabel(category)}</h3>
                <span className="cmdref-group-count">
                  {defs.length} command{defs.length === 1 ? "" : "s"}
                </span>
              </div>
              <ul className="cmdref-grid">
                {defs.map((def) => (
                  <CommandCard key={def.name} def={def} />
                ))}
              </ul>
            </section>
          ))}
          {grouped.size === 0 && (
            <p className="cmdref-empty">
              No commands match <code>{filter}</code>.
            </p>
          )}
        </div>

        <footer className="cmdref-footer">
          <span>Type</span>
          <kbd>/help &lt;command&gt;</kbd>
          <span>for a one-liner. Press</span>
          <kbd>?</kbd>
          <span>for keyboard shortcuts.</span>
        </footer>
      </div>
    </div>
  );
}

function CommandCard({ def }: { def: CommandDef }) {
  return (
    <li className="cmdref-card">
      <header className="cmdref-card-header">
        <code className="cmdref-card-usage">{def.usage}</code>
        <div className="cmdref-card-tags">
          {def.tags.map((t) => (
            <TagPill key={t} tag={t} />
          ))}
        </div>
      </header>
      <p className="cmdref-card-summary">{def.summary}</p>
      {def.longDescription && (
        <p className="cmdref-card-detail">{def.longDescription}</p>
      )}
      {def.aliases.length > 0 && (
        <p className="cmdref-card-aliases">
          Aliases:{" "}
          {def.aliases.map((a, i) => (
            <span key={a}>
              <code>/{a}</code>
              {i < def.aliases.length - 1 && ", "}
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

function TagPill({ tag }: { tag: CommandTag }) {
  return <span className={`cmdref-tag tag-${tag}`}>{tagLabel(tag)}</span>;
}
