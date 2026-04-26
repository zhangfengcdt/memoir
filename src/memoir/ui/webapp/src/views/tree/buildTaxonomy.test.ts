import { describe, expect, it } from "vitest";
import { buildTaxonomy, splitTaxonomyPath, walkTree } from "./buildTaxonomy";
import type { Memory } from "../../api/types";

const mem = (namespace: string, path: string, content = "…"): Memory => ({
  key: `${namespace}:${path}`,
  namespace,
  path,
  content,
  value: {},
});

describe("buildTaxonomy", () => {
  it("returns an empty array for no memories", () => {
    expect(buildTaxonomy([])).toEqual([]);
  });

  it("groups memories by namespace, sorted alphabetically", () => {
    const result = buildTaxonomy([
      mem("default", "a.b"),
      mem("codebase:onboard", "x.y"),
    ]);
    expect(result.map((n) => n.namespace)).toEqual(["codebase:onboard", "default"]);
  });

  it("builds a nested tree from dotted paths", () => {
    const result = buildTaxonomy([
      mem("default", "workflow.coding.style"),
      mem("default", "workflow.coding.naming"),
      mem("default", "workflow.git.commits"),
    ]);
    const [ns] = result;
    expect(ns.namespace).toBe("default");
    expect(ns.count).toBe(3);

    const workflow = ns.root.children[0];
    expect(workflow.name).toBe("workflow");
    expect(workflow.fullPath).toBe("workflow");
    expect(workflow.count).toBe(3);
    expect(workflow.children.map((c) => c.name)).toEqual(["coding", "git"]);

    const coding = workflow.children.find((c) => c.name === "coding")!;
    expect(coding.count).toBe(2);
    expect(coding.children.map((c) => c.name)).toEqual(["naming", "style"]);
  });

  it("aggregates counts through ancestors", () => {
    const result = buildTaxonomy([
      mem("default", "a.b.c"),
      mem("default", "a.b.d"),
      mem("default", "a.e"),
    ]);
    const root = result[0].root;
    const a = root.children[0];
    expect(a.count).toBe(3);

    const b = a.children.find((c) => c.name === "b")!;
    expect(b.count).toBe(2);
    const e = a.children.find((c) => c.name === "e")!;
    expect(e.count).toBe(1);
  });

  it("puts memories in directMemories at the exact terminal path", () => {
    const m = mem("default", "a.b.c");
    const root = buildTaxonomy([m])[0].root;
    const c = root.children[0].children[0].children[0];
    expect(c.directMemories).toEqual([m]);
    expect(root.children[0].children[0].directMemories).toEqual([]); // b has none
  });

  it("supports a memory at the root (single-segment path)", () => {
    const m = mem("default", "identity");
    const root = buildTaxonomy([m])[0].root;
    expect(root.children.length).toBe(1);
    expect(root.children[0].name).toBe("identity");
    expect(root.children[0].directMemories).toEqual([m]);
  });

  it("walkTree visits every node depth-first with depth", () => {
    const result = buildTaxonomy([
      mem("default", "a.b.c"),
      mem("default", "a.d"),
    ]);
    const seen: [string, number][] = [];
    walkTree(result[0].root, (n, depth) => seen.push([n.fullPath, depth]));
    // root, a, a.b, a.b.c, a.d
    expect(seen).toEqual([
      ["", 0],
      ["a", 1],
      ["a.b", 2],
      ["a.b.c", 3],
      ["a.d", 2],
    ]);
  });

  it("handles empty path segments by naming them <empty>", () => {
    const result = buildTaxonomy([mem("default", "a..b")]);
    const root = result[0].root;
    const a = root.children[0];
    expect(a.children[0].name).toBe("<empty>");
    expect(a.children[0].children[0].name).toBe("b");
  });

  it("does not split dots inside a branch-like segment (containing /)", () => {
    // metrics.turn.<branch> keys can carry branch names with dots, e.g.
    // metrics.turn.feature/metric.codebase.stas — the third segment must
    // stay intact instead of expanding into a 5-deep tree.
    const result = buildTaxonomy([
      mem("default", "metrics.turn.feature/metric.codebase.stas"),
      mem("default", "metrics.turn.main"),
    ]);
    const metrics = result[0].root.children.find((c) => c.name === "metrics")!;
    const turn = metrics.children.find((c) => c.name === "turn")!;
    const childNames = turn.children.map((c) => c.name).sort();
    expect(childNames).toEqual([
      "feature/metric.codebase.stas",
      "main",
    ]);
    const featureNode = turn.children.find(
      (c) => c.name === "feature/metric.codebase.stas",
    )!;
    expect(featureNode.fullPath).toBe(
      "metrics.turn.feature/metric.codebase.stas",
    );
    expect(featureNode.children).toHaveLength(0);
  });
});

describe("splitTaxonomyPath", () => {
  it("splits plain dotted paths on every dot", () => {
    expect(splitTaxonomyPath("workflow.coding.style")).toEqual([
      "workflow",
      "coding",
      "style",
    ]);
  });

  it("keeps a slash-bearing leaf intact even when it contains dots", () => {
    expect(
      splitTaxonomyPath("metrics.turn.feature/metric.codebase.stas"),
    ).toEqual(["metrics", "turn", "feature/metric.codebase.stas"]);
  });

  it("does not affect a slash-bearing segment that has no trailing dots", () => {
    expect(splitTaxonomyPath("metrics.turn.feature/x")).toEqual([
      "metrics",
      "turn",
      "feature/x",
    ]);
  });

  it("only fuses from the first slash-bearing segment onward", () => {
    // Hypothetical: an L1 with a slash. Everything from there is one leaf.
    expect(splitTaxonomyPath("a/b.c.d")).toEqual(["a/b.c.d"]);
  });
});
