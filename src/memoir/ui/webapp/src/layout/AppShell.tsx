import { useEffect } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import TopBar from "./TopBar";
import LeftPane from "./LeftPane";
import CommandBar from "./CommandBar";
import MainCanvas from "./MainCanvas";
import RightDrawer from "./RightDrawer";
import { useUI, VIEW_KEYS, isDrawerOpen } from "../state/uiSlice";
import "./AppShell.css";

export default function AppShell() {
  const leftCollapsed = useUI((s) => s.leftCollapsed);
  const drawerOpen = useUI((s) => isDrawerOpen(s.drawerStack));
  const toggleLeft = useUI((s) => s.toggleLeft);
  const closeDrawer = useUI((s) => s.closeDrawer);
  const setActiveView = useUI((s) => s.setActiveView);

  // Global keyboard shortcuts — ⌘B / ⌘1..5 / Esc-closes-drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleLeft();
        return;
      }
      if (mod && /^[1-5]$/.test(e.key)) {
        e.preventDefault();
        const idx = parseInt(e.key, 10) - 1;
        setActiveView(VIEW_KEYS[idx]);
        return;
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
  }, [toggleLeft, closeDrawer, setActiveView]);

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
    </div>
  );
}
