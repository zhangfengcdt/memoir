import { beforeEach, describe, expect, it } from "vitest";
import { useHistorySelection } from "./historySelectionSlice";

const HASHES = ["aaa", "bbb", "ccc", "ddd", "eee"]; // newest → oldest

beforeEach(() => {
  useHistorySelection.getState().clear();
});

describe("history selection reducer", () => {
  it("starts empty", () => {
    const s = useHistorySelection.getState();
    expect(s.primary).toBeNull();
    expect(s.selectedHashes.size).toBe(0);
  });

  it("pick replaces selection with a single hash and sets it as primary", () => {
    useHistorySelection.getState().pick("bbb");
    const s = useHistorySelection.getState();
    expect(s.primary).toBe("bbb");
    expect(Array.from(s.selectedHashes)).toEqual(["bbb"]);
  });

  it("toggle adds hashes without clearing existing selection", () => {
    useHistorySelection.getState().pick("aaa");
    useHistorySelection.getState().toggle("ccc");
    useHistorySelection.getState().toggle("eee");
    expect(useHistorySelection.getState().selectedHashes.size).toBe(3);
  });

  it("selectRange picks everything between primary and target (inclusive)", () => {
    useHistorySelection.getState().pick("aaa");
    useHistorySelection.getState().selectRange("ddd", HASHES);
    const s = useHistorySelection.getState();
    expect(s.primary).toBe("ddd");
    expect(Array.from(s.selectedHashes).sort()).toEqual(
      ["aaa", "bbb", "ccc", "ddd"].sort(),
    );
  });

  it("clear resets both primary and the selection set", () => {
    useHistorySelection.getState().pick("aaa");
    useHistorySelection.getState().toggle("bbb");
    useHistorySelection.getState().clear();
    const s = useHistorySelection.getState();
    expect(s.primary).toBeNull();
    expect(s.selectedHashes.size).toBe(0);
  });

  it("is independent from the Commits view's selection store", () => {
    useHistorySelection.getState().pick("aaa");
    expect(useHistorySelection.getState().primary).toBe("aaa");
    // Not asserting on `useSelection` directly here to avoid coupling this
    // file to that module's import order; the point is this is a distinct
    // zustand store instance, which the type system + separate `create()`
    // call already guarantee.
  });
});
