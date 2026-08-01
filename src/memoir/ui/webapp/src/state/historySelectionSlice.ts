import { create } from "zustand";

/**
 * Selection state for the History view — a separate store from
 * `selectionSlice` (the Commits view's) so switching tabs doesn't blow
 * away either view's in-progress selection. Same shape/semantics as
 * `selectionSlice`; see that file for the click-modifier contract
 * (plain / shift / cmd-click).
 */
export interface HistorySelectionSlice {
  primary: string | null;
  selectedHashes: Set<string>;

  pick: (hash: string) => void;
  toggle: (hash: string) => void;
  selectRange: (hash: string, orderedHashes: string[]) => void;
  clear: () => void;
}

export const useHistorySelection = create<HistorySelectionSlice>((set, get) => ({
  primary: null,
  selectedHashes: new Set(),

  pick(hash) {
    set({ primary: hash, selectedHashes: new Set([hash]) });
  },

  toggle(hash) {
    const next = new Set(get().selectedHashes);
    if (next.has(hash)) {
      next.delete(hash);
      const primary =
        get().primary === hash ? next.values().next().value ?? null : get().primary;
      set({ selectedHashes: next, primary });
    } else {
      next.add(hash);
      set({ selectedHashes: next, primary: get().primary ?? hash });
    }
  },

  selectRange(hash, orderedHashes) {
    const { primary } = get();
    if (!primary) {
      set({ primary: hash, selectedHashes: new Set([hash]) });
      return;
    }
    const a = orderedHashes.indexOf(primary);
    const b = orderedHashes.indexOf(hash);
    if (a < 0 || b < 0) {
      set({ primary: hash, selectedHashes: new Set([hash]) });
      return;
    }
    const [lo, hi] = a < b ? [a, b] : [b, a];
    const range = orderedHashes.slice(lo, hi + 1);
    set({ selectedHashes: new Set(range), primary: hash });
  },

  clear() {
    set({ primary: null, selectedHashes: new Set() });
  },
}));
