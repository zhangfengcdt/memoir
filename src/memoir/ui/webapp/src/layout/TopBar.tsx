import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "./TopBar.css";

export default function TopBar() {
  const storePath = useStore((s) => s.storePath);
  const status = useStore((s) => s.status);
  const data = useStore((s) => s.data);
  const leftCollapsed = useUI((s) => s.leftCollapsed);
  const onToggleLeft = useUI((s) => s.toggleLeft);
  const openStats = useUI((s) => s.openStats);
  const openBranches = useUI((s) => s.openBranches);
  const isRefreshing = useStore((s) => s.status === "connecting");
  const refresh = () => {
    void useStore.getState().refresh();
  };

  const branch = data?.current_branch ?? (status === "connected" ? "—" : "");

  return (
    <header className="topbar" role="banner">
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
          <img
            src="/memoir.png"
            alt="Memoir"
            className="brand-logo"
            draggable={false}
          />
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
        <button
          className="btn btn-ghost btn-sm"
          onClick={refresh}
          title="Refresh store (/refresh)"
          aria-label="Refresh store"
          disabled={!storePath || isRefreshing}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={isRefreshing ? "topbar-spinning" : undefined}
          >
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={openBranches}
          title="Sync branches (/branches)"
          aria-label="Open branch management"
          disabled={!storePath}
        >
          {/* Two-arrow sync icon — top arrow goes right, bottom goes left */}
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
            <polyline points="17 1 21 5 17 9" />
            <path d="M3 11V9a4 4 0 0 1 4-4h14" />
            <polyline points="7 23 3 19 7 15" />
            <path d="M21 13v2a4 4 0 0 1-4 4H3" />
          </svg>
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={openStats}
          title="Statistics (/stats)"
          aria-label="Open statistics"
          disabled={!storePath}
        >
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
            <line x1="18" y1="20" x2="18" y2="10" />
            <line x1="12" y1="20" x2="12" y2="4" />
            <line x1="6" y1="20" x2="6" y2="14" />
          </svg>
        </button>
      </div>
    </header>
  );
}
