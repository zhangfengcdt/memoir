import { describe, expect, it } from "vitest";
import { assignLanes, chronologicalPositions } from "./layout";
import type { Commit } from "../../api/types";

const c = (hash: string, timestamp: number, ...parents: string[]): Commit => ({
  hash,
  short_hash: hash.slice(0, 7),
  message: hash,
  author: "t",
  email: "t@t",
  timestamp,
  parents,
  tags: [],
  refs: [],
});

describe("assignLanes", () => {
  it("puts a linear history on lane 0", () => {
    // HEAD → A → B → C → (root)
    const commits = [c("head", 40, "A"), c("A", 30, "B"), c("B", 20, "C"), c("C", 10)];
    const placed = assignLanes(commits);
    for (const commit of commits) {
      expect(placed.get(commit.hash)?.lane).toBe(0);
    }
  });

  it("puts a branched side-chain on its own lane", () => {
    // Graph:
    //   head  (lane 0)  parents=[A]
    //   side            parents=[A]
    //   A               parents=[]
    const commits = [c("head", 30, "A"), c("side", 25, "A"), c("A", 10)];
    const placed = assignLanes(commits);
    expect(placed.get("head")?.lane).toBe(0);
    expect(placed.get("side")?.lane).toBe(1);
    // A is the first-parent of head, so lane 0 reuses here.
    expect(placed.get("A")?.lane).toBe(0);
  });

  it("merge commit keeps non-first parent on a distinct lane", () => {
    // Graph:
    //   merge   parents=[main-tip, side-tip]
    //   main-tip parents=[base]
    //   side-tip parents=[base]
    //   base
    const commits = [
      c("merge", 50, "main-tip", "side-tip"),
      c("main-tip", 40, "base"),
      c("side-tip", 35, "base"),
      c("base", 10),
    ];
    const placed = assignLanes(commits);
    expect(placed.get("merge")?.lane).toBe(0);
    expect(placed.get("main-tip")?.lane).toBe(0);
    expect(placed.get("side-tip")?.lane).toBe(1);
    // The base is the shared ancestor — the first-parent chain claims it first.
    expect(placed.get("base")?.lane).toBe(0);
  });
});

describe("chronologicalPositions", () => {
  const commits = [c("head", 100), c("mid", 50), c("old", 10)];

  it("leaves placed map unchanged for empty input", () => {
    const placed = assignLanes([]);
    const out = chronologicalPositions([], placed, { width: 800, height: 400 });
    expect(out.size).toBe(0);
  });

  it("maps min timestamp to marginX and max to width-marginX", () => {
    const placed = assignLanes(commits);
    const out = chronologicalPositions(commits, placed, {
      width: 1000,
      height: 400,
      marginX: 50,
    });
    const min = out.get("old")!;
    const max = out.get("head")!;
    expect(min.x).toBe(50);
    expect(max.x).toBe(950);
  });

  it("spaces lanes vertically by laneSpacing", () => {
    const branchCommits = [
      c("head", 30, "A"),
      c("side", 25, "A"),
      c("A", 10),
    ];
    const placed = assignLanes(branchCommits);
    const out = chronologicalPositions(branchCommits, placed, {
      width: 500,
      height: 300,
      marginY: 40,
      laneSpacing: 60,
    });
    expect(out.get("head")!.y).toBe(40); // lane 0 → marginY
    expect(out.get("side")!.y).toBe(100); // lane 1 → marginY + spacing
  });
});
