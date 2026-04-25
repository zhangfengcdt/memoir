import { beforeEach, describe, expect, it } from "vitest";
import {
  drawerPanelTitle,
  isDrawerOpen,
  useUI,
  type DrawerPanel,
} from "./uiSlice";
import type { Commit, Memory } from "../api/types";

const MEMORY: Memory = {
  key: "default:workflow.coding.style",
  namespace: "default",
  path: "workflow.coding.style",
  content: "prefer async-first",
  value: {},
};

const MEMORY_OTHER: Memory = {
  key: "default:identity.name",
  namespace: "default",
  path: "identity.name",
  content: "Feng",
  value: {},
};

const COMMIT_A: Commit = {
  hash: "aaaaaaa",
  short_hash: "aaaaaaa",
  message: "initial",
  author: "t",
  email: "t@t",
  timestamp: 0,
  parents: [],
  tags: [],
  refs: [],
};

const COMMIT_B: Commit = {
  ...COMMIT_A,
  hash: "bbbbbbb",
  short_hash: "bbbbbbb",
  message: "second",
};

beforeEach(() => {
  useUI.getState().closeDrawer();
  useUI.getState().setActiveView("commits");
});

describe("drawer stack reducer", () => {
  it("starts closed", () => {
    expect(isDrawerOpen(useUI.getState().drawerStack)).toBe(false);
  });

  it("pushPanel opens the drawer and sets the top", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    const stack = useUI.getState().drawerStack;
    expect(isDrawerOpen(stack)).toBe(true);
    expect(stack[0].kind).toBe("memory-detail");
  });

  it("pushPanel with a different kind adds to the stack", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    useUI.getState().pushPanel({ kind: "commit-detail", commit: COMMIT_A });
    const stack = useUI.getState().drawerStack;
    expect(stack).toHaveLength(2);
    expect(stack.map((p) => p.kind)).toEqual(["memory-detail", "commit-detail"]);
  });

  it("pushPanel replaces same-kind top instead of stacking", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY_OTHER });
    const stack = useUI.getState().drawerStack;
    expect(stack).toHaveLength(1);
    const top = stack[0] as Extract<DrawerPanel, { kind: "memory-detail" }>;
    expect(top.memory.key).toBe(MEMORY_OTHER.key);
  });

  it("popPanel removes the top and leaves previous panels", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    useUI.getState().pushPanel({ kind: "commit-detail", commit: COMMIT_A });
    useUI.getState().popPanel();
    const stack = useUI.getState().drawerStack;
    expect(stack.map((p) => p.kind)).toEqual(["memory-detail"]);
  });

  it("popPanel on last panel closes the drawer", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    useUI.getState().popPanel();
    expect(isDrawerOpen(useUI.getState().drawerStack)).toBe(false);
  });

  it("closeDrawer clears the whole stack", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    useUI.getState().pushPanel({ kind: "commit-detail", commit: COMMIT_A });
    useUI.getState().closeDrawer();
    expect(useUI.getState().drawerStack).toEqual([]);
  });

  it("gotoPanel trims the stack back to the chosen index", () => {
    useUI.getState().pushPanel({ kind: "memory-detail", memory: MEMORY });
    useUI.getState().pushPanel({ kind: "commit-detail", commit: COMMIT_A });
    useUI.getState().pushPanel({
      kind: "range-diff",
      fromHash: COMMIT_A.hash,
      toHash: COMMIT_B.hash,
    });
    useUI.getState().gotoPanel(0);
    const stack = useUI.getState().drawerStack;
    expect(stack.map((p) => p.kind)).toEqual(["memory-detail"]);
  });

  it("shortcuts overlay opens, toggles, and closes", () => {
    expect(useUI.getState().shortcutsOpen).toBe(false);
    useUI.getState().openShortcuts();
    expect(useUI.getState().shortcutsOpen).toBe(true);
    useUI.getState().closeShortcuts();
    expect(useUI.getState().shortcutsOpen).toBe(false);
    useUI.getState().toggleShortcuts();
    expect(useUI.getState().shortcutsOpen).toBe(true);
    useUI.getState().toggleShortcuts();
    expect(useUI.getState().shortcutsOpen).toBe(false);
  });

  it("stats modal opens, toggles, and closes", () => {
    expect(useUI.getState().statsOpen).toBe(false);
    useUI.getState().openStats();
    expect(useUI.getState().statsOpen).toBe(true);
    useUI.getState().closeStats();
    expect(useUI.getState().statsOpen).toBe(false);
    useUI.getState().toggleStats();
    expect(useUI.getState().statsOpen).toBe(true);
    useUI.getState().toggleStats();
    expect(useUI.getState().statsOpen).toBe(false);
  });

  it("help reference modal opens, toggles, and closes", () => {
    expect(useUI.getState().helpOpen).toBe(false);
    useUI.getState().openHelp();
    expect(useUI.getState().helpOpen).toBe(true);
    useUI.getState().closeHelp();
    expect(useUI.getState().helpOpen).toBe(false);
    useUI.getState().toggleHelp();
    expect(useUI.getState().helpOpen).toBe(true);
    useUI.getState().toggleHelp();
    expect(useUI.getState().helpOpen).toBe(false);
  });

  it("setActiveView and setLeftCollapsed update state synchronously", () => {
    useUI.getState().setActiveView("graph");
    expect(useUI.getState().activeView).toBe("graph");
    useUI.getState().setLeftCollapsed(true);
    expect(useUI.getState().leftCollapsed).toBe(true);
    useUI.getState().toggleLeft();
    expect(useUI.getState().leftCollapsed).toBe(false);
  });

  it("drawerPanelTitle is kind-aware and compact", () => {
    expect(
      drawerPanelTitle({ kind: "memory-detail", memory: MEMORY }),
    ).toBe("workflow.coding.style");
    expect(
      drawerPanelTitle({ kind: "commit-detail", commit: COMMIT_A }),
    ).toBe(`diff @ ${COMMIT_A.short_hash}`);
    expect(
      drawerPanelTitle({
        kind: "range-diff",
        fromHash: "aaaaaaaaaaaa",
        toHash: "bbbbbbbbbbbb",
      }),
    ).toBe("diff aaaaaaa…bbbbbbb");
  });
});
