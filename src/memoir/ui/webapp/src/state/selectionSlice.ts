import { create } from "zustand";

/**
 * Selection state for the Commits view.
 *
 * `primary` is the "anchor" commit — the one whose detail the drawer
 * would render on single-click. `selectedHashes` is the full set for
 * multi-select (used for range diff).
 *
 * Shift-click implements the usual range-select behaviour: select all
 * commits between the current anchor and the clicked one (inclusive).
 * Plain click replaces the selection with just that commit.
 * Cmd/Ctrl-click toggles a single commit without disturbing others.
 */
export interface SelectionSlice {
  primary: string | null;
  selectedHashes: Set<string>;

  /** Clicked with no modifier. Replaces selection with just this commit. */
  pick: (hash: string) => void;
  /** Cmd/Ctrl-click. Toggles this commit in the selection. */
  toggle: (hash: string) => void;
  /** Shift-click. Selects range from primary to this hash (inclusive). */
  selectRange: (hash: string, orderedHashes: string[]) => void;
  /** Drop the whole selection. */
  clear: () => void;
}

export const useSelection = create<SelectionSlice>((set, get) => ({
  primary: null,
  selectedHashes: new Set(),

  pick(hash) {
    set({ primary: hash, selectedHashes: new Set([hash]) });
  },

  toggle(hash) {
    const next = new Set(get().selectedHashes);
    if (next.has(hash)) {
      next.delete(hash);
      // If we just removed the primary, promote the newest remaining.
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
      // No anchor yet — treat like a plain pick.
      set({ primary: hash, selectedHashes: new Set([hash]) });
      return;
    }
    const a = orderedHashes.indexOf(primary);
    const b = orderedHashes.indexOf(hash);
    if (a < 0 || b < 0) {
      // Fall back to single pick if something's out of range.
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
