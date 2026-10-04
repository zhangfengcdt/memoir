import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import MemoryDetail from "./MemoryDetail";
import { useConfig } from "../state/configSlice";
import { useStore } from "../state/storeSlice";
import type { Memory, StoreResponse } from "../api/types";

const MEMORY: Memory = {
  key: "default:workflow.coding.style",
  namespace: "default",
  path: "workflow.coding.style",
  content: "prefer async-first",
  value: {},
};

const DATA = {
  store_path: "feng-zhang/demo",
  branches: ["main"],
  current_branch: "main",
  commits: [],
  namespaces: { default: ["workflow.coding.style"] },
  memories: [MEMORY],
  total_memories: 1,
  tree: {},
  code_repo_branch: null,
} as unknown as StoreResponse;

function connected(storePath: string) {
  useStore.setState({ storePath, status: "connected", data: DATA, error: null });
}

afterEach(() => {
  cleanup();
  useStore.setState({ storePath: null, status: "idle", data: null, error: null });
});

describe("MemoryDetail read-only", () => {
  it("writable: renders the editor and the Update / Forget / Revert controls", () => {
    useConfig.setState({ writable: true, useLLM: false, profile: "local", backUrl: null, features: null });
    connected("/tmp/store");
    render(<MemoryDetail memory={MEMORY} />);
    expect(screen.getByLabelText(/Edit content for/)).toBeTruthy();
    expect(screen.getByText("Update")).toBeTruthy();
    expect(screen.getByText("Forget")).toBeTruthy();
    expect(screen.getByText("Revert")).toBeTruthy();
    expect(screen.queryByTestId("memory-content-readonly")).toBeNull();
  });

  it("read-only (any profile): no editor and no write control, not even disabled", () => {
    for (const profile of ["local", "cloud"] as const) {
      useConfig.setState({ writable: false, useLLM: false, profile, backUrl: null, features: null });
      connected("feng-zhang/demo");
      render(<MemoryDetail memory={MEMORY} />);
      expect(screen.queryByRole("textbox")).toBeNull();
      expect(screen.queryByText("Update")).toBeNull();
      expect(screen.queryByText("Forget")).toBeNull();
      expect(screen.queryByText("Revert")).toBeNull();
      expect(screen.queryByText(/readonly mode/)).toBeNull();
      expect(screen.getByTestId("memory-content-readonly").textContent).toBe("prefer async-first");
      // Reading stays possible.
      expect(screen.getByText("View")).toBeTruthy();
      cleanup();
    }
  });

  it("the LLM rewrite box needs both useLLM and writable", () => {
    useConfig.setState({ writable: false, useLLM: true, profile: "local", backUrl: null, features: null });
    connected("/tmp/store");
    render(<MemoryDetail memory={MEMORY} />);
    expect(screen.queryByText(/Rewrite with AI/)).toBeNull();
  });
});
