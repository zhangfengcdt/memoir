import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The client resolves its API root from `window.__MEMOIR__` at module load,
 * so each case sets the global, resets the module registry and re-imports.
 */
async function loadClientWith(cfg: unknown | undefined) {
  vi.resetModules();
  if (cfg === undefined) {
    delete (window as unknown as { __MEMOIR__?: unknown }).__MEMOIR__;
  } else {
    (window as unknown as { __MEMOIR__?: unknown }).__MEMOIR__ = cfg;
  }
  return import("./client");
}

function okJSON(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client request URLs", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn(async () => okJSON({ success: true }));
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (window as unknown as { __MEMOIR__?: unknown }).__MEMOIR__;
  });

  function calledUrl(i = 0): string {
    return String(fetchSpy.mock.calls[i][0]);
  }

  it("hits /api/* with today's shape when nothing is injected", async () => {
    const { api } = await loadClientWith(undefined);
    await api.store("/tmp/store");
    expect(calledUrl()).toBe("/api/store?path=%2Ftmp%2Fstore");
    await api.commits("/tmp/store", { branch: "main", limit: 5 });
    expect(calledUrl(1)).toBe("/api/commits?path=%2Ftmp%2Fstore&branch=main&limit=5");
    await api.checkout("/tmp/store", "dev");
    expect(calledUrl(2)).toBe("/api/checkout");
    expect(fetchSpy.mock.calls[2][1]).toMatchObject({ method: "POST" });
  });

  it("prefixes every request with apiBase on the cloud and passes ref", async () => {
    const { api } = await loadClientWith({
      apiBase: "/feng-zhang/demo/api",
      store: "feng-zhang/demo",
      ref: "main",
      readonly: true,
      profile: "cloud",
    });
    await api.store("feng-zhang/demo", "experiments");
    expect(calledUrl()).toBe(
      "/feng-zhang/demo/api/store?path=feng-zhang%2Fdemo&ref=experiments",
    );
    await api.currentBranch("feng-zhang/demo", "main");
    expect(calledUrl(1)).toBe("/feng-zhang/demo/api/current-branch?path=feng-zhang%2Fdemo&ref=main");
    await api.branchMergePreview("feng-zhang/demo", "main", "experiments");
    expect(calledUrl(2)).toBe(
      "/feng-zhang/demo/api/branch-merge-preview?path=feng-zhang%2Fdemo&from=main&to=experiments",
    );
    // Same-origin relative URLs: no scheme, no host, so the session cookie rides along.
    for (const call of fetchSpy.mock.calls) expect(String(call[0])).toMatch(/^\//);
  });

  it("omits ref entirely when it is null or undefined", async () => {
    const { api } = await loadClientWith({ apiBase: "/h/n/api", profile: "cloud" });
    await api.store("h/n", null);
    expect(calledUrl()).toBe("/h/n/api/store?path=h%2Fn");
    await api.store("h/n");
    expect(calledUrl(1)).toBe("/h/n/api/store?path=h%2Fn");
  });

  it("surfaces the server's error field as MemoirApiError", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: false, error: "store not found" }), {
        status: 404,
      }),
    );
    const { api, MemoirApiError } = await loadClientWith({ apiBase: "/h/n/api", profile: "cloud" });
    const err = await api.store("h/n").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(MemoirApiError);
    expect(String(err)).toMatch(/store not found/);
    expect((err as InstanceType<typeof MemoirApiError>).status).toBe(404);
  });
});
