import { useStore } from "../state/storeSlice";
import "./TopBar.css";

interface TopBarProps {
  onToggleLeft: () => void;
  leftCollapsed: boolean;
}

export default function TopBar({ onToggleLeft, leftCollapsed }: TopBarProps) {
  const storePath = useStore((s) => s.storePath);
  const status = useStore((s) => s.status);
  const data = useStore((s) => s.data);

  const branch = data?.current_branch ?? (status === "connected" ? "—" : "");
  const memoryCount = data?.total_memories;

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button
          className="topbar-toggle"
          onClick={onToggleLeft}
          aria-label={leftCollapsed ? "Expand left pane" : "Collapse left pane"}
          title={leftCollapsed ? "Expand (⌘B)" : "Collapse (⌘B)"}
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
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <line x1="9" y1="4" x2="9" y2="20" />
          </svg>
        </button>
        <div className="topbar-brand">
          <span className="brand-mark" aria-hidden="true">
            ◆
          </span>
          <span className="brand-name">Memoir</span>
        </div>
        <div className="topbar-store">
          <span className="eyebrow">Store</span>
          <code
            className="store-path"
            data-status={status}
            title={storePath ?? "Not connected"}
          >
            {storePath ?? "not connected"}
          </code>
        </div>
      </div>

      <div className="topbar-right">
        {branch && (
          <button className="btn btn-ghost btn-sm" title="Current branch">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="6" y1="3" x2="6" y2="15" />
              <circle cx="18" cy="6" r="3" />
              <circle cx="6" cy="18" r="3" />
              <path d="M18 9a9 9 0 0 1-9 9" />
            </svg>
            <span>{branch}</span>
          </button>
        )}
        {typeof memoryCount === "number" && (
          <span className="chip" title="Total memories in store">
            {memoryCount} mem
          </span>
        )}
      </div>
    </header>
  );
}
