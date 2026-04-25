import { beforeEach, describe, expect, it } from "vitest";
import { useSelection } from "./selectionSlice";

const HASHES = ["aaa", "bbb", "ccc", "ddd", "eee"]; // newest → oldest

beforeEach(() => {
  useSelection.getState().clear();
});

describe("selection reducer", () => {
  it("starts empty", () => {
    const s = useSelection.getState();
    expect(s.primary).toBeNull();
    expect(s.selectedHashes.size).toBe(0);
  });

  it("pick replaces selection with a single hash and sets it as primary", () => {
    useSelection.getState().pick("bbb");
    const s = useSelection.getState();
    expect(s.primary).toBe("bbb");
    expect(Array.from(s.selectedHashes)).toEqual(["bbb"]);
  });

  it("pick replaces any prior selection", () => {
    useSelection.getState().pick("aaa");
    useSelection.getState().pick("ccc");
    const s = useSelection.getState();
    expect(s.primary).toBe("ccc");
    expect(Array.from(s.selectedHashes)).toEqual(["ccc"]);
  });

  it("toggle adds hashes without clearing existing selection", () => {
    useSelection.getState().pick("aaa");
    useSelection.getState().toggle("ccc");
    useSelection.getState().toggle("eee");
    expect(useSelection.getState().selectedHashes.size).toBe(3);
  });

  it("toggle removes a hash; if removing the primary, promotes another", () => {
    useSelection.getState().pick("aaa");
    useSelection.getState().toggle("bbb");
    expect(useSelection.getState().primary).toBe("aaa");
    useSelection.getState().toggle("aaa");
    const s = useSelection.getState();
    expect(s.primary).toBe("bbb");
    expect(s.selectedHashes.has("aaa")).toBe(false);
    expect(s.selectedHashes.has("bbb")).toBe(true);
  });

  it("selectRange picks everything between primary and target (inclusive)", () => {
    useSelection.getState().pick("aaa");
    useSelection.getState().selectRange("ddd", HASHES);
    const s = useSelection.getState();
    expect(s.primary).toBe("ddd");
    expect(Array.from(s.selectedHashes).sort()).toEqual(
      ["aaa", "bbb", "ccc", "ddd"].sort(),
    );
  });

  it("selectRange works backwards too", () => {
    useSelection.getState().pick("ddd");
    useSelection.getState().selectRange("bbb", HASHES);
    expect(Array.from(useSelection.getState().selectedHashes).sort()).toEqual(
      ["bbb", "ccc", "ddd"].sort(),
    );
  });

  it("selectRange with no primary degrades to pick", () => {
    useSelection.getState().selectRange("ccc", HASHES);
    const s = useSelection.getState();
    expect(s.primary).toBe("ccc");
    expect(Array.from(s.selectedHashes)).toEqual(["ccc"]);
  });

  it("clear resets both primary and the selection set", () => {
    useSelection.getState().pick("aaa");
    useSelection.getState().toggle("bbb");
    useSelection.getState().clear();
    const s = useSelection.getState();
    expect(s.primary).toBeNull();
    expect(s.selectedHashes.size).toBe(0);
  });
});
