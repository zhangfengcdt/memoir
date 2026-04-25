import type {
  ApiError,
  BranchesResponse,
  CommitsResponse,
  CurrentBranchResponse,
  RangeDiffResponse,
  StoreResponse,
} from "./types";

/**
 * Thin typed wrapper around `fetch` for memoir's `/api/*` endpoints.
 *
 * All reads require a `path` query parameter pointing at a memoir store
 * on disk — that's the backend contract, not a UI-level convenience. The
 * client sends the path as-is; URL encoding happens in `URLSearchParams`.
 *
 * Errors are raised as `MemoirApiError`. Callers handle them with a
 * try/catch and a toast; the command registry centralises this so
 * individual views don't repeat the pattern.
 */
export class MemoirApiError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(status: number, url: string, message: string) {
    super(`[${status}] ${url}: ${message}`);
    this.status = status;
    this.url = url;
    this.name = "MemoirApiError";
  }
}

async function getJSON<T>(path: string, params: Record<string, string>): Promise<T> {
  const qs = new URLSearchParams(params).toString();
  const url = qs ? `${path}?${qs}` : path;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  if (!res.ok) {
    // Backend sometimes returns JSON error bodies, sometimes plain text.
    let detail = res.statusText;
    try {
      const body = (await res.json()) as Partial<ApiError>;
      if (body?.error) detail = body.error;
    } catch {
      /* fall back to statusText */
    }
    throw new MemoirApiError(res.status, url, detail);
  }

  return (await res.json()) as T;
}

export const api = {
  store: (path: string) => getJSON<StoreResponse>("/api/store", { path }),

  branches: (path: string) => getJSON<BranchesResponse>("/api/branches", { path }),

  currentBranch: (path: string) =>
    getJSON<CurrentBranchResponse>("/api/current-branch", { path }),

  commits: (path: string, opts: { branch?: string; limit?: number } = {}) =>
    getJSON<CommitsResponse>("/api/commits", {
      path,
      branch: opts.branch ?? "HEAD",
      limit: String(opts.limit ?? 20),
    }),

  rangeDiff: async (
    path: string,
    fromRef: string,
    toRef: string,
  ): Promise<RangeDiffResponse> => {
    // Server-side keys are `from`/`to`; we normalize to fromRef/toRef in the
    // response so the rest of the codebase doesn't fight TS keywords.
    const raw = await getJSON<Omit<RangeDiffResponse, "fromRef" | "toRef"> & {
      from: string;
      to: string;
    }>("/api/commit-range-diff", { path, from: fromRef, to: toRef });
    const { from, to, ...rest } = raw;
    return { ...rest, fromRef: from, toRef: to };
  },
};
