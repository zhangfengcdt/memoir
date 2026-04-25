import { create } from "zustand";
import { api, MemoirApiError } from "../api/client";
import type { StoreResponse } from "../api/types";

export type ConnectionStatus = "idle" | "connecting" | "connected" | "error";

export interface HistoryEntry {
  id: number;
  // The command the user typed (already includes leading `/`).
  input: string;
  // Severity for tinting the output row.
  level: "info" | "success" | "warning" | "error";
  // One or more short lines to display.
  lines: string[];
  timestamp: number;
}

interface StoreSlice {
  // Connection
  storePath: string | null;
  status: ConnectionStatus;
  error: string | null;
  // Last fetched payload — null before connect, populated by connect/refresh
  data: StoreResponse | null;
  /** Bumps on every successful connect/refresh. Views that have their
   * own fetch lifecycle (CommitList) watch this in their effect deps so
   * a "Refresh" click on the toolbar picks them up too. */
  revision: number;

  // Command history (scrollable record of what the user ran)
  history: HistoryEntry[];

  // Actions
  connect: (path: string) => Promise<void>;
  /**
   * Re-read the connected store.
   *
   * ``silent: true`` is for auto-poll: if the new payload is identical to
   * the current one (same commits, same memory contents, same namespaces),
   * the store stays at its existing state — no setState, no revision
   * bump, no status flicker, no history entry. Views never re-render
   * when nothing has actually changed.
   */
  refresh: (opts?: { silent?: boolean }) => Promise<void>;
  disconnect: () => void;
  pushHistory: (entry: Omit<HistoryEntry, "id" | "timestamp">) => void;
  clearHistory: () => void;
}

let nextHistoryId = 1;

// Rehydrate `storePath` from URL on first load — `memoir ui` passes the
// connected store as `?store=<path>` and we want the shell to auto-connect
// without requiring the user to retype it.
function initialStorePath(): string | null {
  if (typeof window === "undefined") return null;
  const p = new URL(window.location.href).searchParams.get("store");
  return p && p.length > 0 ? p : null;
}

/**
 * "Did anything the UI cares about actually change between two store
 * payloads?" — used by silent auto-poll to skip no-op refreshes.
 *
 * Compares the fields views render: branch state, commit topology
 * (count + tip hash), namespace shape, and per-memory content. Anything
 * else (e.g., regenerated timestamps on identical reads) is ignored.
 */
function isMaterialChange(
  prev: StoreResponse | null,
  next: StoreResponse,
): boolean {
  if (!prev) return true;
  if (prev.current_branch !== next.current_branch) return true;
  if (prev.total_memories !== next.total_memories) return true;
  if (prev.branches.length !== next.branches.length) return true;
  for (let i = 0; i < prev.branches.length; i++) {
    if (prev.branches[i] !== next.branches[i]) return true;
  }
  if (prev.commits.length !== next.commits.length) return true;
  if (prev.commits[0]?.hash !== next.commits[0]?.hash) return true;
  // Namespace shape — keys + per-namespace path lists.
  const prevKeys = Object.keys(prev.namespaces).sort();
  const nextKeys = Object.keys(next.namespaces).sort();
  if (prevKeys.length !== nextKeys.length) return true;
  for (let i = 0; i < prevKeys.length; i++) {
    if (prevKeys[i] !== nextKeys[i]) return true;
    const a = prev.namespaces[prevKeys[i]] ?? [];
    const b = next.namespaces[prevKeys[i]] ?? [];
    if (a.length !== b.length) return true;
  }
  // Memory contents — Map lookup on the prev set keeps this O(n).
  if (prev.memories.length !== next.memories.length) return true;
  const prevByKey = new Map(prev.memories.map((m) => [m.key, m.content ?? ""]));
  for (const m of next.memories) {
    if (prevByKey.get(m.key) !== (m.content ?? "")) return true;
  }
  return false;
}

export const useStore = create<StoreSlice>((set, get) => ({
  storePath: initialStorePath(),
  status: "idle",
  error: null,
  data: null,
  revision: 0,
  history: [],

  async connect(path: string) {
    set({ status: "connecting", error: null, storePath: path });
    try {
      const data = await api.store(path);
      set((s) => ({
        status: "connected",
        data,
        error: null,
        revision: s.revision + 1,
      }));
      get().pushHistory({
        input: `/connect ${path}`,
        level: "success",
        lines: [
          `Connected to ${data.store_path}`,
          `branch=${data.current_branch} · memories=${data.total_memories} · commits=${data.commits.length}`,
        ],
      });
    } catch (err) {
      const message = err instanceof MemoirApiError ? err.message : String(err);
      set({ status: "error", error: message, data: null });
      get().pushHistory({
        input: `/connect ${path}`,
        level: "error",
        lines: [message],
      });
    }
  },

  async refresh(opts) {
    const silent = opts?.silent ?? false;
    const path = get().storePath;
    if (!path) {
      if (!silent) {
        get().pushHistory({
          input: "/refresh",
          level: "warning",
          lines: ["No store connected. Run /connect <path> first."],
        });
      }
      return;
    }
    // Silent polls don't flip status to "connecting" — the spinner
    // only shows for user-initiated refreshes.
    if (!silent) set({ status: "connecting", error: null });
    try {
      const data = await api.store(path);
      const changed = isMaterialChange(get().data, data);
      if (!changed && silent) {
        // No-op for silent polls when nothing changed: keep state
        // referentially identical so React skips re-renders.
        return;
      }
      set((s) => ({
        status: "connected",
        data,
        error: null,
        // Only bump revision when the data actually changed —
        // otherwise downstream views (CommitList) would re-fetch
        // for no reason.
        revision: changed ? s.revision + 1 : s.revision,
      }));
      if (!silent) {
        get().pushHistory({
          input: "/refresh",
          level: "success",
          lines: [
            `Reloaded ${data.store_path}`,
            `branch=${data.current_branch} · memories=${data.total_memories}`,
          ],
        });
      }
    } catch (err) {
      const message = err instanceof MemoirApiError ? err.message : String(err);
      // Don't loudly clobber state on a transient silent-poll failure;
      // the next tick will retry.
      if (silent) return;
      set({ status: "error", error: message });
      get().pushHistory({
        input: "/refresh",
        level: "error",
        lines: [message],
      });
    }
  },

  disconnect() {
    set({ storePath: null, status: "idle", data: null, error: null });
    get().pushHistory({
      input: "/disconnect",
      level: "info",
      lines: ["Disconnected from store."],
    });
  },

  pushHistory(entry) {
    set((s) => ({
      history: [
        ...s.history,
        {
          ...entry,
          id: nextHistoryId++,
          timestamp: Date.now(),
        },
      ].slice(-200), // keep the last 200 entries
    }));
  },

  clearHistory() {
    set({ history: [] });
  },
}));
