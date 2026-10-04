import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import TopBar from "./TopBar";
import { useConfig } from "../state/configSlice";
import { useStore } from "../state/storeSlice";
import type { StoreResponse } from "../api/types";

const DATA = {
  store_path: "feng-zhang/demo",
  branches: ["main", "experiments"],
  current_branch: "main",
  commits: [],
  namespaces: {},
  memories: [],
  total_memories: 0,
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

describe("TopBar profiles", () => {
  it("local writable: statistics, branch switcher and sync are offered; no back link", () => {
    useConfig.setState({ writable: true, useLLM: false, profile: "local", backUrl: null, features: null });
    connected("/tmp/store");
    render(<TopBar />);
    expect(screen.getByLabelText("Open statistics")).toBeTruthy();
    expect(screen.getByLabelText("Switch branch")).toBeTruthy();
    expect(screen.getByLabelText("Open branch management")).toBeTruthy();
    expect(screen.queryByText("Back to store", { exact: false })).toBeNull();
    expect(screen.queryByText("Read-only")).toBeNull();
  });

  it("local read-only: no branch switcher (checkout is a write), read-only badge shown", () => {
    useConfig.setState({ writable: false, useLLM: false, profile: "local", backUrl: null, features: null });
    connected("/tmp/store");
    render(<TopBar />);
    expect(screen.queryByLabelText("Switch branch")).toBeNull();
    expect(screen.getByText("Read-only")).toBeTruthy();
    // Branches stays available as a read: it opens branches-status.
    expect(screen.getByLabelText("Open branches")).toBeTruthy();
  });

  it("cloud: address + back link, branch viewing as a read, no statistics, no edition badge", () => {
    useConfig.setState({
      writable: false,
      useLLM: false,
      profile: "cloud",
      backUrl: "/feng-zhang/demo",
      features: null,
    });
    connected("feng-zhang/demo");
    render(<TopBar />);
    expect(screen.getByText("feng-zhang/demo")).toBeTruthy();
    const back = screen.getByText("Back to store", { exact: false }) as HTMLAnchorElement;
    expect(back.getAttribute("href")).toBe("/feng-zhang/demo");
    expect(screen.queryByLabelText("Open statistics")).toBeNull();
    expect(screen.queryByText("Community Version")).toBeNull();
    expect(screen.getByLabelText("View another branch")).toBeTruthy();
    // The branch name still shows even though the Statistics button (its usual home) is gone.
    expect(screen.getByTitle("Current branch").textContent).toBe("main");
  });

  it("the logo resolves against Vite's base so /workspace/ builds find it", () => {
    useConfig.setState({ writable: true, useLLM: false, profile: "local", backUrl: null, features: null });
    render(<TopBar />);
    const img = screen.getByAltText("Memoir") as HTMLImageElement;
    expect(img.getAttribute("src")).toBe(`${import.meta.env.BASE_URL}memoir.png`);
  });

  it("cloud with features: [\"statistics\"] shows the Statistics button", () => {
    useConfig.setState({
      writable: false,
      useLLM: false,
      profile: "cloud",
      backUrl: "/feng-zhang/demo",
      features: ["statistics"],
    });
    connected("feng-zhang/demo");
    render(<TopBar />);
    expect(screen.getByLabelText("Open statistics")).toBeTruthy();
    expect(screen.queryByTitle("Current branch")).toBeNull();
  });
});
