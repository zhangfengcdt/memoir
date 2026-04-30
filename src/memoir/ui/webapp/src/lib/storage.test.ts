import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeStorage } from "./storage";

interface Prefs {
  view: "a" | "b";
  count: number;
}

const KEY = "memoir:test:prefs";
const DEFAULTS: Prefs = { view: "a", count: 0 };

const validate = (raw: unknown): Prefs | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.view !== "a" && obj.view !== "b") return null;
  if (typeof obj.count !== "number") return null;
  return { view: obj.view, count: obj.count };
};

// jsdom's localStorage in this vitest version is partial (.removeItem and
// .clear missing). Install a minimal in-memory shim so tests are
// independent of which jsdom we're on.
function installMemoryStorage() {
  const data = new Map<string, string>();
  const fake: Storage = {
    get length() {
      return data.size;
    },
    key: (i: number) => Array.from(data.keys())[i] ?? null,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, String(v));
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
    clear: () => {
      data.clear();
    },
  };
  vi.stubGlobal("localStorage", fake);
}

beforeEach(() => {
  installMemoryStorage();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("makeStorage", () => {
  it("returns defaults when nothing is stored", () => {
    const s = makeStorage(KEY, DEFAULTS, validate);
    expect(s.load()).toEqual(DEFAULTS);
  });

  it("round-trips a saved value", () => {
    const s = makeStorage(KEY, DEFAULTS, validate);
    s.save({ view: "b", count: 5 });
    expect(s.load()).toEqual({ view: "b", count: 5 });
  });

  it("falls back to defaults when JSON is malformed", () => {
    localStorage.setItem(KEY, "{not json");
    const s = makeStorage(KEY, DEFAULTS, validate);
    expect(s.load()).toEqual(DEFAULTS);
  });

  it("falls back when the validator rejects", () => {
    localStorage.setItem(KEY, JSON.stringify({ view: "z", count: "wat" }));
    const s = makeStorage(KEY, DEFAULTS, validate);
    expect(s.load()).toEqual(DEFAULTS);
  });

  it("clear removes the key", () => {
    const s = makeStorage(KEY, DEFAULTS, validate);
    s.save({ view: "b", count: 7 });
    s.clear();
    expect(s.load()).toEqual(DEFAULTS);
  });

  it("works without a validator (trusts JSON shape)", () => {
    const s = makeStorage(KEY, DEFAULTS);
    s.save({ view: "b", count: 9 });
    expect(s.load()).toEqual({ view: "b", count: 9 });
  });
});
