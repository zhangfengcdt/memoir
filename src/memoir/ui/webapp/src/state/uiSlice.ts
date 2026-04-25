import { create } from "zustand";

/**
 * UI chrome state — view tabs, left pane collapse, right drawer visibility.
 *
 * Separated from storeSlice (which tracks server-side state) so that
 * changing the active tab from a slash command doesn't risk racing with
 * a fetch in flight.
 */
export type ViewKey = "commits" | "tree" | "graph" | "timeline" | "places";

export const VIEW_KEYS: ViewKey[] = [
  "commits",
  "tree",
  "graph",
  "timeline",
  "places",
];

interface UISlice {
  activeView: ViewKey;
  leftCollapsed: boolean;
  drawerOpen: boolean;

  setActiveView: (view: ViewKey) => void;
  toggleLeft: () => void;
  setLeftCollapsed: (collapsed: boolean) => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleDrawer: () => void;
}

export const useUI = create<UISlice>((set) => ({
  activeView: "commits",
  leftCollapsed: false,
  drawerOpen: false,

  setActiveView(view) {
    set({ activeView: view });
  },
  toggleLeft() {
    set((s) => ({ leftCollapsed: !s.leftCollapsed }));
  },
  setLeftCollapsed(collapsed) {
    set({ leftCollapsed: collapsed });
  },
  openDrawer() {
    set({ drawerOpen: true });
  },
  closeDrawer() {
    set({ drawerOpen: false });
  },
  toggleDrawer() {
    set((s) => ({ drawerOpen: !s.drawerOpen }));
  },
}));
