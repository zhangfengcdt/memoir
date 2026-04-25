import { useEffect, useRef } from "react";
import {
  PanelGroup,
  Panel,
  PanelResizeHandle,
  type ImperativePanelHandle,
} from "react-resizable-panels";
import TopBar from "./TopBar";
import LeftPane from "./LeftPane";
import CommandBar from "./CommandBar";
import MainCanvas from "./MainCanvas";
import RightDrawer from "./RightDrawer";
import StatsModal from "../modals/StatsModal";
import CommandReferenceModal from "../modals/CommandReferenceModal";
import SyncBranchesModal from "../modals/SyncBranchesModal";
import BranchCommitsModal from "../modals/BranchCommitsModal";
import LiveAnnouncer from "./LiveAnnouncer";
import { useUI, VISIBLE_VIEW_KEYS, isDrawerOpen } from "../state/uiSlice";
import { useConfig } from "../state/configSlice";
import "./AppShell.css";

export default function AppShell() {
  const leftCollapsed = useUI((s) => s.leftCollapsed);
  const drawerOpen = useUI((s) => isDrawerOpen(s.drawerStack));
  const toggleLeft = useUI((s) => s.toggleLeft);
  const closeDrawer = useUI((s) => s.closeDrawer);
  const setActiveView = useUI((s) => s.setActiveView);
  const setLeftCollapsed = useUI((s) => s.setLeftCollapsed);

  // react-resizable-panels owns the actual width of each panel; just
  // toggling our state changes content but won't change the size. We
  // drive collapse/expand via the imperative handle so the panel
  // genuinely shrinks to its collapsedSize and back.
  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  useEffect(() => {
    const panel = leftPanelRef.current;
    if (!panel) return;
    if (leftCollapsed && !panel.isCollapsed()) {
      panel.collapse();
    } else if (!leftCollapsed && panel.isCollapsed()) {
      panel.expand();
    }
  }, [leftCollapsed]);
  // The command bar is the natural-language + slash-command input. We
  // hide it when the server was launched without ``--usellm`` because
  // the natural-language path needs the LLM and most slash commands
  // surface elsewhere (TopBar buttons, view tabs, autocomplete).
  const useLLM = useConfig((s) => s.useLLM);

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
            ref={leftPanelRef}
            defaultSize={22}
            minSize={14}
            maxSize={40}
            collapsible
            collapsedSize={4}
            // Threshold below which the panel snaps fully closed — gives
            // a satisfying "click into rail mode" feel when dragging.
            onCollapse={() => setLeftCollapsed(true)}
            onExpand={() => setLeftCollapsed(false)}
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

      {useLLM && <CommandBar />}

      <StatsModal />
      <CommandReferenceModal />
      <SyncBranchesModal />
      <BranchCommitsModal />
      <LiveAnnouncer />
    </div>
  );
}
