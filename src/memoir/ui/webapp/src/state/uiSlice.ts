import { create } from "zustand";
import type { Commit, Memory } from "../api/types";

/**
 * UI chrome state — view tabs, left pane collapse, drawer stack.
 *
 * Separated from storeSlice (which tracks server-side state) so that
 * changing the active tab or drawer from a slash command doesn't risk
 * racing with a fetch in flight.
 */
export type ViewKey = "commits" | "tree" | "graph" | "timeline" | "places";

export const VIEW_KEYS: ViewKey[] = [
  "commits",
  "tree",
  "graph",
  "timeline",
  "places",
];

/**
 * A single slide-in panel on the drawer stack. The drawer shows the
 * top-most panel; the breadcrumb lists everything below so users can
 * jump back with one click.
 */
export type DrawerPanel =
  | { kind: "memory-detail"; memory: Memory }
  | { kind: "commit-detail"; commit: Commit }
  | { kind: "range-diff"; fromHash: string; toHash: string };

export function drawerPanelTitle(panel: DrawerPanel): string {
  switch (panel.kind) {
    case "memory-detail":
      return panel.memory.path || panel.memory.key;
    case "commit-detail":
      return panel.commit.short_hash;
    case "range-diff":
      return `diff ${panel.fromHash.slice(0, 7)}…${panel.toHash.slice(0, 7)}`;
  }
}

interface UISlice {
  activeView: ViewKey;
  leftCollapsed: boolean;
  drawerStack: DrawerPanel[];

  setActiveView: (view: ViewKey) => void;
  toggleLeft: () => void;
  setLeftCollapsed: (collapsed: boolean) => void;

  /** Push a panel on top. If the top already has the same panel-kind and
   * the same identifying key, replace it instead — avoids breadcrumb
   * noise when a selection change fires rapidly. */
  pushPanel: (panel: DrawerPanel) => void;
  /** Pop the topmost panel. Closes the drawer if the stack empties. */
  popPanel: () => void;
  /** Close the drawer entirely. */
  closeDrawer: () => void;
  /** Jump back to the panel at ``index`` (removing everything above it). */
  gotoPanel: (index: number) => void;
}

function panelIdentity(p: DrawerPanel): string {
  switch (p.kind) {
    case "memory-detail":
      return `memory:${p.memory.key}`;
    case "commit-detail":
      return `commit:${p.commit.hash}`;
    case "range-diff":
      return `range:${p.fromHash}:${p.toHash}`;
  }
}

export const useUI = create<UISlice>((set) => ({
  activeView: "commits",
  leftCollapsed: false,
  drawerStack: [],

  setActiveView(view) {
    set({ activeView: view });
  },
  toggleLeft() {
    set((s) => ({ leftCollapsed: !s.leftCollapsed }));
  },
  setLeftCollapsed(collapsed) {
    set({ leftCollapsed: collapsed });
  },

  pushPanel(panel) {
    set((s) => {
      const stack = [...s.drawerStack];
      const top = stack[stack.length - 1];
      // Replace the top if it's the same kind + identity — prevents the
      // breadcrumb from ballooning as the user clicks around.
      if (top && top.kind === panel.kind && panelIdentity(top) === panelIdentity(panel)) {
        stack[stack.length - 1] = panel;
      } else if (top && top.kind === panel.kind) {
        // Same kind, different identity → still replace rather than stack.
        stack[stack.length - 1] = panel;
      } else {
        stack.push(panel);
      }
      return { drawerStack: stack };
    });
  },

  popPanel() {
    set((s) => ({
      drawerStack: s.drawerStack.slice(0, -1),
    }));
  },

  closeDrawer() {
    set({ drawerStack: [] });
  },

  gotoPanel(index) {
    set((s) => ({
      drawerStack: s.drawerStack.slice(0, index + 1),
    }));
  },
}));

/** Convenience: is the drawer currently open? */
export function isDrawerOpen(stack: DrawerPanel[]): boolean {
  return stack.length > 0;
}
