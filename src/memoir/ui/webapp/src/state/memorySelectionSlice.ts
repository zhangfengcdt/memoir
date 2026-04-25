import { create } from "zustand";
import type { Memory } from "../api/types";

/**
 * Selection state for the Tree view — "which memory is the user focused on?"
 *
 * Intentionally separate from the commit selection slice:
 * - different lifetime (memory selection survives tab switches; commit
 *   selection resets on branch checkout),
 * - different semantics (single-select typical; multi-select is a Phase
 *   5/6 concern once the drawer can diff two memories).
 */
export interface MemorySelectionSlice {
  selected: Memory | null;
  select: (memory: Memory | null) => void;
  clear: () => void;
}

export const useMemorySelection = create<MemorySelectionSlice>((set) => ({
  selected: null,
  select(memory) {
    set({ selected: memory });
  },
  clear() {
    set({ selected: null });
  },
}));
