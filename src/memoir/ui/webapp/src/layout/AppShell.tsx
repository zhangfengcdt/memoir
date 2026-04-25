import { useState } from "react";
import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";
import TopBar from "./TopBar";
import LeftPane from "./LeftPane";
import CommandBar from "./CommandBar";
import MainCanvas from "./MainCanvas";
import RightDrawer from "./RightDrawer";
import "./AppShell.css";

export default function AppShell() {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="app-shell">
      <TopBar
        onToggleLeft={() => setLeftCollapsed((v) => !v)}
        leftCollapsed={leftCollapsed}
      />

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
            <LeftPane collapsed={leftCollapsed} />
          </Panel>

          <PanelResizeHandle className="resize-handle resize-handle-v" />

          <Panel id="main" order={2} minSize={30} className="pane">
            <MainCanvas onOpenDrawer={() => setDrawerOpen(true)} />
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
                <RightDrawer onClose={() => setDrawerOpen(false)} />
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      <CommandBar />
    </div>
  );
}
