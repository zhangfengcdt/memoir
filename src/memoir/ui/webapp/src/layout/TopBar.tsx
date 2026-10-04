import { useRef, useState } from "react";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import { useConfig } from "../state/configSlice";
import { branchSwitchIsRead, featureEnabled } from "../config/runtime";
import BranchSwitcher from "./BranchSwitcher";
import BranchMatchToggle from "./BranchMatchToggle";
import "./TopBar.css";

// Resolved against Vite's `base` so the logo works under `/workspace/` too.
const LOGO_URL = `${import.meta.env.BASE_URL}memoir.png`;

export default function TopBar() {
  const storePath = useStore((s) => s.storePath);
  const writable = useConfig((s) => s.writable);
  const profile = useConfig((s) => s.profile);
  const backUrl = useConfig((s) => s.backUrl);
  const cloud = profile === "cloud";
  // Switching branches is a write locally (checkout) and a read on the cloud.
  const canSwitchBranch = writable || branchSwitchIsRead(profile);
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

  const [switcherOpen, setSwitcherOpen] = useState(false);
  const switcherAnchorRef = useRef<HTMLButtonElement | null>(null);

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
            src={LOGO_URL}
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
          {cloud && backUrl && (
            <a className="topbar-back" href={backUrl} title="Back to the store page">
              ← Back to store
            </a>
          )}
        </div>
      </div>

      <div className="topbar-right">
        {!cloud && (
          <span
            className="topbar-edition"
            title="Memoir Community Version"
            aria-label="Memoir Community Version"
          >
            Community Version
          </span>
        )}
        {!writable && (
          <span className="topbar-edition" title="Read-only: no changes can be made here">
            Read-only
          </span>
        )}
        {branch && !featureEnabled("statistics", profile) && (
          <span className="topbar-branch" title="Current branch">
            {branch}
          </span>
        )}
        {branch && featureEnabled("statistics", profile) && (
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
        <BranchMatchToggle />
        {canSwitchBranch && (
        <div className="topbar-switcher-wrap">
          <button
            ref={switcherAnchorRef}
            className="btn btn-ghost btn-sm"
            onClick={() => setSwitcherOpen((v) => !v)}
            title={cloud ? "View another branch" : "Switch branch"}
            aria-label={cloud ? "View another branch" : "Switch branch"}
            aria-haspopup="listbox"
            aria-expanded={switcherOpen}
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
            >
              <polyline points="7 15 12 20 17 15" />
              <polyline points="7 9 12 4 17 9" />
            </svg>
          </button>
          <BranchSwitcher
            open={switcherOpen}
            onClose={() => setSwitcherOpen(false)}
            anchorRef={switcherAnchorRef}
          />
        </div>
        )}
        <button
          className="btn btn-ghost btn-sm"
          onClick={openBranches}
          title={writable ? "Sync branches (/branches)" : "Branches (/branches)"}
          aria-label={writable ? "Open branch management" : "Open branches"}
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
      </div>
    </header>
  );
}
