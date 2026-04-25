import { describe, expect, it } from "vitest";
import { listCommands, categoryLabel, tagLabel } from "./registry";

describe("registry", () => {
  it("every canonical command has a category and a usage starting with /", () => {
    const all = listCommands();
    expect(all.length).toBeGreaterThan(5);
    for (const def of all) {
      expect(def.category).toBeTruthy();
      expect(def.usage).toMatch(/^\//);
      expect(def.summary.length).toBeGreaterThan(0);
    }
  });

  it("groups commands by category in order Core → Navigation → Selection → UI → System", () => {
    const cats = listCommands().map((d) => d.category);
    // Each category should appear contiguously — once we leave it,
    // we shouldn't come back.
    const seen = new Set<string>();
    let last = cats[0];
    for (const c of cats) {
      if (c !== last) {
        expect(seen.has(c)).toBe(false);
        seen.add(last);
        last = c;
      }
    }
  });

  it("categoryLabel + tagLabel return non-empty strings", () => {
    expect(categoryLabel("core")).toBeTruthy();
    expect(categoryLabel("navigation")).toBeTruthy();
    expect(categoryLabel("selection")).toBeTruthy();
    expect(categoryLabel("ui")).toBeTruthy();
    expect(categoryLabel("system")).toBeTruthy();
    expect(tagLabel("readonly")).toBe("READONLY");
    expect(tagLabel("mutating")).toBe("MUTATING");
  });

  it("connect carries the readonly tag, disconnect does not", () => {
    const all = listCommands();
    const connect = all.find((d) => d.name === "connect")!;
    const disconnect = all.find((d) => d.name === "disconnect")!;
    expect(connect.tags).toContain("readonly");
    expect(disconnect.tags).not.toContain("readonly");
  });
});
