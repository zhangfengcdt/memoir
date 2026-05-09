import { describe, expect, it } from "vitest";
import { compileWildcard } from "./wildcard";

describe("compileWildcard", () => {
  it("returns null for empty / whitespace-only patterns", () => {
    expect(compileWildcard("")).toBeNull();
    expect(compileWildcard("   ")).toBeNull();
  });

  it("treats wildcard-free patterns as substring matches", () => {
    const m = compileWildcard("workflow.coding")!;
    expect(m("workflow.coding")).toBe(true);
    // Substring semantics — extra prefix/suffix is fine.
    expect(m("workflow.coding.style")).toBe(true);
    expect(m("a.workflow.coding")).toBe(true);
    expect(m("metrics.turn.main")).toBe(false);
  });

  it("substring match still escapes regex specials (so a+b is literal)", () => {
    const m = compileWildcard("a+b")!;
    expect(m("a+b")).toBe(true);
    expect(m("xa+by")).toBe(true);
    expect(m("aaab")).toBe(false);
  });

  it("expands * to match any sequence including dots", () => {
    const m = compileWildcard("workflow.*")!;
    expect(m("workflow.coding")).toBe(true);
    expect(m("workflow.coding.style")).toBe(true);
    expect(m("workflow")).toBe(false);
    expect(m("metrics.turn")).toBe(false);
  });

  it("expands ? to exactly one character", () => {
    const m = compileWildcard("a.?")!;
    expect(m("a.b")).toBe(true);
    expect(m("a.bc")).toBe(false);
    expect(m("a.")).toBe(false);
  });

  it("matches case-insensitively", () => {
    const m = compileWildcard("Workflow.*")!;
    expect(m("workflow.coding")).toBe(true);
  });

  it("preserves dots as literals (so workflow.* doesn't catch workflowx)", () => {
    const m = compileWildcard("workflow.*")!;
    expect(m("workflowx")).toBe(false);
  });

  it("anchors the match when an explicit wildcard is present", () => {
    // ``*.style`` should only match paths ending in ``.style``, not ones
    // that merely contain ``.style`` somewhere (otherwise there'd be no
    // way to opt out of substring mode).
    const m = compileWildcard("*.style")!;
    expect(m("workflow.coding.style")).toBe(true);
    expect(m("workflow.style.notes")).toBe(false);
  });
});
