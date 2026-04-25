import { useEffect } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import TopBar from "./TopBar";
import LeftPane from "./LeftPane";
import CommandBar from "./CommandBar";
import MainCanvas from "./MainCanvas";
import RightDrawer from "./RightDrawer";
import ShortcutsOverlay from "../modals/ShortcutsOverlay";
import StatsModal from "../modals/StatsModal";
import CommandReferenceModal from "../modals/CommandReferenceModal";
import LiveAnnouncer from "./LiveAnnouncer";
import { useUI, VISIBLE_VIEW_KEYS, isDrawerOpen } from "../state/uiSlice";
import "./AppShell.css";

export default function AppShell() {
  const leftCollapsed = useUI((s) => s.leftCollapsed);
  const drawerOpen = useUI((s) => isDrawerOpen(s.drawerStack));
  const toggleLeft = useUI((s) => s.toggleLeft);
  const closeDrawer = useUI((s) => s.closeDrawer);
  const setActiveView = useUI((s) => s.setActiveView);
  const openShortcuts = useUI((s) => s.openShortcuts);

  // Global keyboard shortcuts — ⌘B / ⌘1..5 / Esc-closes-drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleLeft();
        return;
      }
      if (mod && /^[1-9]$/.test(e.key)) {
        const idx = parseInt(e.key, 10) - 1;
        const target = VISIBLE_VIEW_KEYS[idx];
        if (target) {
          e.preventDefault();
          setActiveView(target);
        }
        return;
      }
      // ``?`` opens the shortcuts overlay, but only when focus is outside
      // an editable element — otherwise the user is just typing text.
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const active = document.activeElement as HTMLElement | null;
        const isEditable =
          active?.tagName === "INPUT" ||
          active?.tagName === "TEXTAREA" ||
          (active && active.isContentEditable);
        if (!isEditable) {
          e.preventDefault();
          openShortcuts();
          return;
        }
      }
      if (e.key === "Escape" && useUI.getState().drawerStack.length > 0) {
        // Only close the drawer if no input is focused — otherwise Esc is
        // owned by the CommandBar (clears its buffer).
        const active = document.activeElement as HTMLElement | null;
        if (active?.tagName !== "INPUT" && active?.tagName !== "TEXTAREA") {
          closeDrawer();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleLeft, closeDrawer, setActiveView, openShortcuts]);

  return (
    <div className="app-shell">
      <TopBar />

      <div className="app-body">
        <PanelGroup direction="horizontal" autoSaveId="memoir:shell">
          <Panel
            id="left"
            order={1}
            defaultSize={22}
            minSize={leftCollapsed ? 4 : 14}
            maxSize={40}
            collapsible
            collapsedSize={4}
            className="pane"
          >
            <LeftPane />
          </Panel>

          <PanelResizeHandle className="resize-handle resize-handle-v" />

          <Panel id="main" order={2} minSize={30} className="pane">
            <MainCanvas />
          </Panel>

          {drawerOpen && (
            <>
              <PanelResizeHandle className="resize-handle resize-handle-v" />
              <Panel
                id="drawer"
                order={3}
                defaultSize={28}
                minSize={18}
                maxSize={45}
                className="pane"
              >
                <RightDrawer />
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      <CommandBar />

      <ShortcutsOverlay />
      <StatsModal />
      <CommandReferenceModal />
      <LiveAnnouncer />
    </div>
  );
}
