/**
 * Tiny typed wrapper around ``localStorage`` with safe fallbacks.
 *
 * Why not Zustand's ``persist`` middleware? We only persist a couple of
 * UI prefs and want full control over migration if the shape ever
 * changes — a 30-line helper keeps deps minimal and testing trivial.
 *
 * Failure modes handled:
 * - ``localStorage`` unavailable (privacy-mode browsers) → no-op.
 * - Stored JSON is malformed (corrupted by external write) → ``defaults``.
 * - Stored shape doesn't validate (post-update with renamed keys) →
 *   the caller's ``validate`` returns ``null`` and we fall back.
 */
export interface StorageAdapter<T> {
  load(): T;
  save(value: T): void;
  clear(): void;
}

export function makeStorage<T>(
  key: string,
  defaults: T,
  /** Optional shape-check; return null to discard the stored value. */
  validate?: (raw: unknown) => T | null,
): StorageAdapter<T> {
  const safe = hasLocalStorage();

  return {
    load() {
      if (!safe) return defaults;
      try {
        const raw = window.localStorage.getItem(key);
        if (raw === null) return defaults;
        const parsed: unknown = JSON.parse(raw);
        if (validate) {
          const validated = validate(parsed);
          return validated === null ? defaults : validated;
        }
        // Without a validator, trust the caller's type. ``parsed`` is
        // unknown so we cast — same risk as parsing JSON anywhere.
        return parsed as T;
      } catch {
        return defaults;
      }
    },

    save(value) {
      if (!safe) return;
      try {
        window.localStorage.setItem(key, JSON.stringify(value));
      } catch {
        // Quota exceeded or other failures — drop silently. Persistence
        // is a best-effort UX win, not a correctness requirement.
      }
    },

    clear() {
      if (!safe) return;
      try {
        window.localStorage.removeItem(key);
      } catch {
        /* see ``save`` */
      }
    },
  };
}

function hasLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && !!window.localStorage;
  } catch {
    return false;
  }
}
