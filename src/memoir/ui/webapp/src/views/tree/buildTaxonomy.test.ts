import { describe, expect, it } from "vitest";
import { buildTaxonomy, walkTree } from "./buildTaxonomy";
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
});
