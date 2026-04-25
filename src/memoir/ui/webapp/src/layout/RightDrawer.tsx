import { useEffect, useRef } from "react";
import { useUI, drawerPanelTitle, type DrawerPanel } from "../state/uiSlice";
import MemoryDetail from "../drawers/MemoryDetail";
import CommitDetail from "../drawers/CommitDetail";
import RangeDiff from "../drawers/RangeDiff";
import "./RightDrawer.css";

export default function RightDrawer() {
  const stack = useUI((s) => s.drawerStack);
  const closeDrawer = useUI((s) => s.closeDrawer);
  const gotoPanel = useUI((s) => s.gotoPanel);
  const popPanel = useUI((s) => s.popPanel);

  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);

  // Snapshot the trigger element on first open, then focus the close
  // button so keyboard users land somewhere actionable. On close,
  // return focus to whatever opened the drawer (the Tree leaf or
  // commit row that was clicked) so screen-reader / keyboard users
  // don't lose their place.
  const isOpen = stack.length > 0;
  useEffect(() => {
    if (isOpen && !wasOpen.current) {
      triggerRef.current = document.activeElement as HTMLElement | null;
      // Defer one frame so the button is mounted before we focus.
      requestAnimationFrame(() => closeBtnRef.current?.focus());
      wasOpen.current = true;
    } else if (!isOpen && wasOpen.current) {
      // Close: restore focus to the trigger.
      triggerRef.current?.focus?.();
      wasOpen.current = false;
    }
  }, [isOpen]);

  const top = stack[stack.length - 1];
  if (!top) return null;

  return (
    <aside className="drawer" aria-label="Detail drawer">
      <header className="drawer-header">
        <nav className="drawer-breadcrumb" aria-label="Drawer breadcrumb">
          {stack.map((panel, i) => {
            const isLast = i === stack.length - 1;
            const title = drawerPanelTitle(panel);
            return (
              <span key={`${panel.kind}-${i}`} className="breadcrumb-segment">
                {!isLast ? (
                  <button
                    type="button"
                    className="breadcrumb-link"
                    onClick={() => gotoPanel(i)}
                    title={`Go back to ${title}`}
                  >
                    <span className="breadcrumb-kind">{kindLabel(panel)}</span>
                    <span className="breadcrumb-title">{title}</span>
                  </button>
                ) : (
                  <span className="breadcrumb-current">
                    <span className="breadcrumb-kind">{kindLabel(panel)}</span>
                    <span className="breadcrumb-title">{title}</span>
                  </span>
                )}
                {!isLast && (
                  <span className="breadcrumb-sep" aria-hidden="true">
                    /
                  </span>
                )}
              </span>
            );
          })}
        </nav>

        <div className="drawer-header-actions">
          {stack.length > 1 && (
            <button
              type="button"
              className="drawer-action"
              onClick={popPanel}
              aria-label="Back"
              title="Back (pop panel)"
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
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
            </button>
          )}
          <button
            ref={closeBtnRef}
            type="button"
            className="drawer-close"
            onClick={closeDrawer}
            aria-label="Close drawer"
            title="Close (esc)"
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
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </header>

      <div className="drawer-body">
        <PanelRenderer panel={top} />
      </div>
    </aside>
  );
}

function PanelRenderer({ panel }: { panel: DrawerPanel }) {
  switch (panel.kind) {
    case "memory-detail":
      return <MemoryDetail memory={panel.memory} />;
    case "commit-detail":
      return <CommitDetail commit={panel.commit} />;
    case "range-diff":
      return <RangeDiff fromHash={panel.fromHash} toHash={panel.toHash} />;
  }
}

function kindLabel(panel: DrawerPanel): string {
  switch (panel.kind) {
    case "memory-detail":
      return "memory";
    case "commit-detail":
      return "commit";
    case "range-diff":
      return "diff";
  }
}
