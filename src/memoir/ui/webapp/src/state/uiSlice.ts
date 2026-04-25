import { create } from "zustand";
import type { Commit, Memory } from "../api/types";
import { makeStorage } from "../lib/storage";

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

/** Shape of the slice's persisted prefs. Drawer stack and shortcuts
 * overlay are runtime-only. */
interface PersistedUI {
  activeView: ViewKey;
  leftCollapsed: boolean;
}

const PERSIST_KEY = "memoir:ui:v1";

const persist = makeStorage<PersistedUI>(
  PERSIST_KEY,
  { activeView: "commits", leftCollapsed: false },
  (raw) => {
    if (!raw || typeof raw !== "object") return null;
    const obj = raw as Record<string, unknown>;
    const view = obj.activeView;
    const collapsed = obj.leftCollapsed;
    if (typeof view !== "string" || !VIEW_KEYS.includes(view as ViewKey)) {
      return null;
    }
    if (typeof collapsed !== "boolean") return null;
    return { activeView: view as ViewKey, leftCollapsed: collapsed };
  },
);

interface UISlice {
  activeView: ViewKey;
  leftCollapsed: boolean;
  drawerStack: DrawerPanel[];
  shortcutsOpen: boolean;
  statsOpen: boolean;

  setActiveView: (view: ViewKey) => void;
  toggleLeft: () => void;
  setLeftCollapsed: (collapsed: boolean) => void;
  openShortcuts: () => void;
  closeShortcuts: () => void;
  toggleShortcuts: () => void;
  openStats: () => void;
  closeStats: () => void;
  toggleStats: () => void;

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

// Hydrate from localStorage at module load — once per session. Tests
// can override by calling ``persist.clear()`` then reloading the module.
const initial = persist.load();

function persistFromState(s: { activeView: ViewKey; leftCollapsed: boolean }) {
  persist.save({ activeView: s.activeView, leftCollapsed: s.leftCollapsed });
}

export const useUI = create<UISlice>((set) => ({
  activeView: initial.activeView,
  leftCollapsed: initial.leftCollapsed,
  drawerStack: [],
  shortcutsOpen: false,
  statsOpen: false,

  setActiveView(view) {
    set({ activeView: view });
    persistFromState({ activeView: view, leftCollapsed: useUI.getState().leftCollapsed });
  },
  toggleLeft() {
    set((s) => {
      const next = !s.leftCollapsed;
      persistFromState({ activeView: s.activeView, leftCollapsed: next });
      return { leftCollapsed: next };
    });
  },
  setLeftCollapsed(collapsed) {
    set((s) => {
      persistFromState({ activeView: s.activeView, leftCollapsed: collapsed });
      return { leftCollapsed: collapsed };
    });
  },
  openShortcuts() {
    set({ shortcutsOpen: true });
  },
  closeShortcuts() {
    set({ shortcutsOpen: false });
  },
  toggleShortcuts() {
    set((s) => ({ shortcutsOpen: !s.shortcutsOpen }));
  },
  openStats() {
    set({ statsOpen: true });
  },
  closeStats() {
    set({ statsOpen: false });
  },
  toggleStats() {
    set((s) => ({ statsOpen: !s.statsOpen }));
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
