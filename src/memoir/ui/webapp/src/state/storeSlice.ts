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

  // Command history (scrollable record of what the user ran)
  history: HistoryEntry[];

  // Actions
  connect: (path: string) => Promise<void>;
  refresh: () => Promise<void>;
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

export const useStore = create<StoreSlice>((set, get) => ({
  storePath: initialStorePath(),
  status: "idle",
  error: null,
  data: null,
  history: [],

  async connect(path: string) {
    set({ status: "connecting", error: null, storePath: path });
    try {
      const data = await api.store(path);
      set({ status: "connected", data, error: null });
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

  async refresh() {
    const path = get().storePath;
    if (!path) {
      get().pushHistory({
        input: "/refresh",
        level: "warning",
        lines: ["No store connected. Run /connect <path> first."],
      });
      return;
    }
    set({ status: "connecting", error: null });
    try {
      const data = await api.store(path);
      set({ status: "connected", data, error: null });
      get().pushHistory({
        input: "/refresh",
        level: "success",
        lines: [
          `Reloaded ${data.store_path}`,
          `branch=${data.current_branch} · memories=${data.total_memories}`,
        ],
      });
    } catch (err) {
      const message = err instanceof MemoirApiError ? err.message : String(err);
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
