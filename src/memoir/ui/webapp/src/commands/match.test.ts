import { describe, expect, it } from "vitest";
import { matchCommands } from "./match";
import { listCommands } from "./registry";

describe("matchCommands", () => {
  it("returns no matches for empty / non-slash input", () => {
    expect(matchCommands("")).toEqual([]);
    expect(matchCommands("hello")).toEqual([]);
  });

  it("returns every command for bare /", () => {
    const all = listCommands();
    expect(matchCommands("/").length).toBe(all.length);
  });

  it("filters by canonical-name prefix", () => {
    const m = matchCommands("/co");
    const names = m.map((d) => d.name);
    expect(names).toContain("connect");
    expect(names).toContain("commits");
    // status doesn't start with co; filtered out
    expect(names).not.toContain("status");
  });

  it("ranks canonical-name matches before alias-only matches and preserves category order", () => {
    // /co: both 'connect' (core category) and 'commits' (navigation
    // category) match by canonical name. listCommands sorts by category
    // first, so 'connect' (core) ranks above 'commits' (navigation).
    const m = matchCommands("/co");
    expect(m[0].name).toBe("connect");
    expect(m.some((d) => d.name === "commits")).toBe(true);
  });

  it("returns nothing once a space appears (user is on args)", () => {
    expect(matchCommands("/connect ")).toEqual([]);
    expect(matchCommands("/connect /tmp/foo")).toEqual([]);
  });

  it("alias 'log' matches commits via alias-only path", () => {
    const m = matchCommands("/lo");
    const names = m.map((d) => d.name);
    expect(names).toContain("commits");
  });

  it("non-matching prefix returns []", () => {
    expect(matchCommands("/xyzzz")).toEqual([]);
  });
});
