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
export type ViewKey =
  | "commits"
  | "tree"
  | "graph"
  | "watch"
  | "timeline"
  | "places";

/** All views the app can switch to. Slash commands like ``/timeline``
 * still set these; only the visible tab list narrows them. */
export const VIEW_KEYS: ViewKey[] = [
  "commits",
  "tree",
  "graph",
  "watch",
  "timeline",
  "places",
];

/** Subset rendered in the tab bar and the collapsed-rail. Timeline and
 * Places are deferred for a later phase — their views still compile so
 * we don't have to delete the work. */
export const VISIBLE_VIEW_KEYS: ViewKey[] = ["commits", "tree", "graph", "watch"];

/** Polling interval in ms when ``autoRefresh`` is on. Three seconds is
 * the same cadence the legacy UI's auto-poll used. */
export const AUTO_REFRESH_MS = 3000;

/**
 * Maximum taxonomy depth shown in the Outline / Map views.
 *   "all" → unlimited (default)
 *   1/2/3 → keep paths trimmed to that many segments
 */
export type DepthFilter = "all" | 1 | 2 | 3;

export const DEPTH_OPTIONS: DepthFilter[] = ["all", 1, 2, 3];

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
      // Reads as "diff @ 9c2a107" in the breadcrumb so users know the
      // panel shows the commit's diff, not just metadata.
      return `diff @ ${panel.commit.short_hash}`;
    case "range-diff":
      return `diff ${panel.fromHash.slice(0, 7)}…${panel.toHash.slice(0, 7)}`;
  }
}

/** Shape of the slice's persisted prefs. Drawer stack and shortcuts
 * overlay are runtime-only. */
interface PersistedUI {
  activeView: ViewKey;
  leftCollapsed: boolean;
  selectedNamespace: string | null;
  keyInclude: string;
  keyExclude: string;
  depthFilter: DepthFilter;
}

const PERSIST_KEY = "memoir:ui:v1";

function isDepthFilter(v: unknown): v is DepthFilter {
  return v === "all" || v === 1 || v === 2 || v === 3;
}

const persist = makeStorage<PersistedUI>(
  PERSIST_KEY,
  // First-launch defaults: open on Commits, expanded pane, and pre-select
  // the ``default`` namespace so the Tree view shows real data right away
  // (the most common case is the user only ever has the ``default`` ns).
  // Users can still pick "All namespaces" — that choice persists.
  {
    activeView: "commits",
    leftCollapsed: false,
    selectedNamespace: "default",
    keyInclude: "",
    keyExclude: "",
    depthFilter: "all",
  },
  (raw) => {
    if (!raw || typeof raw !== "object") return null;
    const obj = raw as Record<string, unknown>;
    const view = obj.activeView;
    const collapsed = obj.leftCollapsed;
    const ns = obj.selectedNamespace;
    if (typeof view !== "string" || !VIEW_KEYS.includes(view as ViewKey)) {
      return null;
    }
    if (typeof collapsed !== "boolean") return null;
    if (ns !== null && typeof ns !== "string") return null;
    // Filter fields are optional for forward-compat with prefs written
    // by older builds; missing values fall back to the defaults.
    const keyInclude = typeof obj.keyInclude === "string" ? obj.keyInclude : "";
    const keyExclude = typeof obj.keyExclude === "string" ? obj.keyExclude : "";
    const depthFilter = isDepthFilter(obj.depthFilter) ? obj.depthFilter : "all";
    return {
      activeView: view as ViewKey,
      leftCollapsed: collapsed,
      selectedNamespace: ns,
      keyInclude,
      keyExclude,
      depthFilter,
    };
  },
);

interface UISlice {
  activeView: ViewKey;
  leftCollapsed: boolean;
  drawerStack: DrawerPanel[];
  statsOpen: boolean;
  helpOpen: boolean;
  branchesOpen: boolean;
  /** Name of the branch whose unmerged commits are shown in the
   * BranchCommitsModal. ``null`` = modal closed. */
  branchCommitsTarget: string | null;
  /** When true, the active view re-fetches every ``AUTO_REFRESH_MS``.
   * Session-only — not persisted, since polling has a real cost and
   * silently surviving reloads would surprise users. */
  autoRefresh: boolean;
  /** Namespace filter for the right-hand views.
   *  ``null`` means "All namespaces". Persists across reloads. */
  selectedNamespace: string | null;
  /** Wildcard pattern that memory paths must match to appear in the
   *  Outline / Map views. Empty = no filter. Persists. */
  keyInclude: string;
  /** Wildcard pattern that memory paths must NOT match. Empty = no
   *  filter. Applied after ``keyInclude``. Persists. */
  keyExclude: string;
  /** Maximum taxonomy depth shown in the Outline / Map views. Persists. */
  depthFilter: DepthFilter;

  setActiveView: (view: ViewKey) => void;
  toggleLeft: () => void;
  setLeftCollapsed: (collapsed: boolean) => void;
  setSelectedNamespace: (ns: string | null) => void;
  setKeyInclude: (pattern: string) => void;
  setKeyExclude: (pattern: string) => void;
  setDepthFilter: (depth: DepthFilter) => void;
  clearFilters: () => void;
  openStats: () => void;
  closeStats: () => void;
  toggleStats: () => void;
  openHelp: () => void;
  closeHelp: () => void;
  toggleHelp: () => void;
  openBranches: () => void;
  closeBranches: () => void;
  toggleBranches: () => void;
  openBranchCommits: (branch: string) => void;
  closeBranchCommits: () => void;
  setAutoRefresh: (on: boolean) => void;
  toggleAutoRefresh: () => void;

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

function persistFromState(s: PersistedUI) {
  persist.save(s);
}

function snapshot(state: UISlice): PersistedUI {
  return {
    activeView: state.activeView,
    leftCollapsed: state.leftCollapsed,
    selectedNamespace: state.selectedNamespace,
    keyInclude: state.keyInclude,
    keyExclude: state.keyExclude,
    depthFilter: state.depthFilter,
  };
}

export const useUI = create<UISlice>((set) => ({
  activeView: initial.activeView,
  leftCollapsed: initial.leftCollapsed,
  drawerStack: [],
  statsOpen: false,
  helpOpen: false,
  branchesOpen: false,
  branchCommitsTarget: null,
  autoRefresh: false,
  selectedNamespace: initial.selectedNamespace,
  keyInclude: initial.keyInclude,
  keyExclude: initial.keyExclude,
  depthFilter: initial.depthFilter,

  setActiveView(view) {
    set({ activeView: view });
    persistFromState(snapshot(useUI.getState()));
  },
  toggleLeft() {
    set((s) => ({ leftCollapsed: !s.leftCollapsed }));
    persistFromState(snapshot(useUI.getState()));
  },
  setLeftCollapsed(collapsed) {
    set({ leftCollapsed: collapsed });
    persistFromState(snapshot(useUI.getState()));
  },
  setSelectedNamespace(ns) {
    set({ selectedNamespace: ns });
    persistFromState(snapshot(useUI.getState()));
  },
  setKeyInclude(pattern) {
    set({ keyInclude: pattern });
    persistFromState(snapshot(useUI.getState()));
  },
  setKeyExclude(pattern) {
    set({ keyExclude: pattern });
    persistFromState(snapshot(useUI.getState()));
  },
  setDepthFilter(depth) {
    set({ depthFilter: depth });
    persistFromState(snapshot(useUI.getState()));
  },
  clearFilters() {
    set({ keyInclude: "", keyExclude: "", depthFilter: "all" });
    persistFromState(snapshot(useUI.getState()));
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
  openHelp() {
    set({ helpOpen: true });
  },
  closeHelp() {
    set({ helpOpen: false });
  },
  toggleHelp() {
    set((s) => ({ helpOpen: !s.helpOpen }));
  },
  openBranches() {
    set({ branchesOpen: true });
  },
  closeBranches() {
    set({ branchesOpen: false });
  },
  toggleBranches() {
    set((s) => ({ branchesOpen: !s.branchesOpen }));
  },
  openBranchCommits(branch) {
    set({ branchCommitsTarget: branch });
  },
  closeBranchCommits() {
    set({ branchCommitsTarget: null });
  },
  setAutoRefresh(on) {
    set({ autoRefresh: on });
  },
  toggleAutoRefresh() {
    set((s) => ({ autoRefresh: !s.autoRefresh }));
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
