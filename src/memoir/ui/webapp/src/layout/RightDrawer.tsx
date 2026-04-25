import { useUI } from "../state/uiSlice";
import "./RightDrawer.css";

export default function RightDrawer() {
  const onClose = useUI((s) => s.closeDrawer);
  return (
    <aside className="drawer" aria-label="Detail drawer">
      <header className="drawer-header">
        <div className="drawer-breadcrumb">
          <span className="eyebrow">Detail</span>
          <span className="drawer-title">Memory preview</span>
        </div>
        <button
          className="drawer-close"
          onClick={onClose}
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
      </header>

      <div className="drawer-body">
        <p className="drawer-empty">
          Drawer preview — this replaces the modal stack in the current UI.
          Selecting a memory, running <code>/diff</code>, or viewing proof will
          open here.
        </p>
      </div>
    </aside>
  );
}
