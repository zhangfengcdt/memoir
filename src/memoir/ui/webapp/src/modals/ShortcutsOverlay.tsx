import { useEffect, useRef } from "react";
import { useUI } from "../state/uiSlice";
import "./ShortcutsOverlay.css";

interface Shortcut {
  keys: string[];
  description: string;
}

interface Group {
  title: string;
  items: Shortcut[];
}

const GROUPS: Group[] = [
  {
    title: "Navigation",
    items: [
      { keys: ["⌘", "1"], description: "Switch to Commits view" },
      { keys: ["⌘", "2"], description: "Switch to Tree view" },
      { keys: ["⌘", "3"], description: "Switch to Graph view" },
      { keys: ["⌘", "4"], description: "Switch to Timeline view" },
      { keys: ["⌘", "5"], description: "Switch to Places view" },
      { keys: ["⌘", "B"], description: "Collapse / expand the left pane" },
    ],
  },
  {
    title: "Command bar",
    items: [
      { keys: ["⌘", "K"], description: "Focus the command input" },
      { keys: ["↑"], description: "Previous command in history" },
      { keys: ["↓"], description: "Next command in history" },
      { keys: ["esc"], description: "Clear the command input" },
    ],
  },
  {
    title: "Commits view",
    items: [
      { keys: ["click"], description: "Select commit + open in drawer" },
      { keys: ["shift", "click"], description: "Range-select commits" },
      { keys: ["⌘", "click"], description: "Toggle commit in selection" },
      { keys: ["↑", "/", "↓"], description: "Move primary selection (focused row)" },
    ],
  },
  {
    title: "Drawer",
    items: [
      { keys: ["esc"], description: "Close the drawer (when focus is outside an input)" },
      { keys: ["click breadcrumb"], description: "Jump back to a previous panel" },
    ],
  },
  {
    title: "Other",
    items: [
      { keys: ["?"], description: "Show this shortcuts overlay" },
      { keys: ["/"], description: "Type a slash command (autocomplete in /help)" },
    ],
  },
];

export default function ShortcutsOverlay() {
  const open = useUI((s) => s.shortcutsOpen);
  const close = useUI((s) => s.closeShortcuts);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previousActive.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousActive.current?.focus();
    };
  }, [open, close]);

  if (!open) return null;

  return (
    <div
      className="shortcuts-backdrop"
      role="presentation"
      onClick={(e) => {
        // Click on backdrop only — clicks inside the dialog shouldn't close.
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className="shortcuts-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        tabIndex={-1}
      >
        <header className="shortcuts-header">
          <h2 id="shortcuts-title" className="shortcuts-title">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            className="shortcuts-close"
            onClick={close}
            aria-label="Close shortcuts overlay"
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

        <div className="shortcuts-grid">
          {GROUPS.map((group) => (
            <section key={group.title} className="shortcuts-group">
              <h3 className="shortcuts-group-title">{group.title}</h3>
              <dl className="shortcuts-list">
                {group.items.map((item, i) => (
                  <div key={i} className="shortcuts-row">
                    <dt className="shortcuts-keys">
                      {item.keys.map((k, j) => (
                        <span key={j}>
                          {j > 0 && (
                            <span className="shortcuts-sep" aria-hidden="true">
                              +
                            </span>
                          )}
                          <kbd>{k}</kbd>
                        </span>
                      ))}
                    </dt>
                    <dd className="shortcuts-desc">{item.description}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>

        <footer className="shortcuts-footer">
          <span>Press</span>
          <kbd>?</kbd>
          <span>any time to bring this back. Type</span>
          <kbd>/help</kbd>
          <span>for slash commands.</span>
        </footer>
      </div>
    </div>
  );
}
