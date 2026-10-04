import { describe, expect, it } from "vitest";
import {
  apiUrl,
  branchSwitchIsRead,
  featureEnabled,
  readRuntimeConfig,
} from "./runtime";

function fakeWindow(cfg: unknown): Window {
  return { __MEMOIR__: cfg } as unknown as Window;
}

describe("readRuntimeConfig", () => {
  it("falls back to local defaults without window.__MEMOIR__", () => {
    const rt = readRuntimeConfig(undefined);
    expect(rt).toEqual({
      apiBase: "",
      store: null,
      ref: null,
      readonly: null,
      profile: "local",
      backUrl: null,
      injected: false,
    });
    expect(readRuntimeConfig({} as Window).injected).toBe(false);
  });

  it("reads the cloud Workspace object as the server injects it", () => {
    const rt = readRuntimeConfig(
      fakeWindow({
        apiBase: "/feng-zhang/demo/api",
        store: "feng-zhang/demo",
        ref: "main",
        readonly: true,
        profile: "cloud",
        backUrl: "/feng-zhang/demo",
      }),
    );
    expect(rt).toEqual({
      apiBase: "/feng-zhang/demo/api",
      store: "feng-zhang/demo",
      ref: "main",
      readonly: true,
      profile: "cloud",
      backUrl: "/feng-zhang/demo",
      injected: true,
    });
  });

  it("tolerates null ref, a trailing slash on apiBase, and unknown profiles", () => {
    const rt = readRuntimeConfig(
      fakeWindow({ apiBase: "/x/y/api/", ref: null, profile: "weird", readonly: "yes" }),
    );
    expect(rt.apiBase).toBe("/x/y/api");
    expect(rt.ref).toBeNull();
    expect(rt.profile).toBe("local");
    expect(rt.readonly).toBeNull(); // not a boolean → "read the URL"
    expect(rt.injected).toBe(true);
  });
});

describe("apiUrl", () => {
  it("uses /api locally and the injected base on the cloud", () => {
    expect(apiUrl("store", "/api")).toBe("/api/store");
    expect(apiUrl("watch/list", "/api")).toBe("/api/watch/list");
    expect(apiUrl("store", "/feng-zhang/demo/api")).toBe("/feng-zhang/demo/api/store");
    expect(apiUrl("/commits", "/feng-zhang/demo/api")).toBe("/feng-zhang/demo/api/commits");
  });
});

describe("profiles", () => {
  it("the cloud profile lacks exactly the features its API does not serve", () => {
    for (const f of [
      "statistics",
      "timeline",
      "places",
      "watch",
      "blame",
      "llm",
      "crypto",
      "branch-match",
      "code-repo",
    ] as const) {
      expect(featureEnabled(f, "cloud")).toBe(false);
      expect(featureEnabled(f, "local")).toBe(true);
    }
  });

  it("branch switching is a read only on the cloud", () => {
    expect(branchSwitchIsRead("cloud")).toBe(true);
    expect(branchSwitchIsRead("local")).toBe(false);
  });
});
