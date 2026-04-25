import type {
  ApiError,
  BranchesResponse,
  CommitsResponse,
  CurrentBranchResponse,
  LocationResponse,
  RangeDiffResponse,
  StatisticsResponse,
  StoreResponse,
  TimelineResponse,
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
  return parseResponse<T>(res, url);
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  return parseResponse<T>(res, path);
}

async function parseResponse<T>(res: Response, url: string): Promise<T> {
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

  statistics: (path: string) =>
    getJSON<StatisticsResponse>("/api/statistics", { path }),

  /**
   * Timeline + location endpoints can 500 on stores that have no
   * memento data initialised. Treat that as an empty-state rather than
   * a hard error so the UI can render its empty state cleanly. Real
   * structural errors (4xx, network failures) still raise.
   */
  timeline: async (path: string): Promise<TimelineResponse> => {
    try {
      return await getJSON<TimelineResponse>("/api/timeline", { path });
    } catch (err) {
      if (err instanceof MemoirApiError && err.status >= 500) {
        return {
          success: true,
          summary: null,
          timeline_data: {},
          start_date: null,
          end_date: null,
        };
      }
      throw err;
    }
  },

  locations: async (path: string): Promise<LocationResponse> => {
    try {
      return await getJSON<LocationResponse>("/api/location", { path });
    } catch (err) {
      if (err instanceof MemoirApiError && err.status >= 500) {
        return { success: true, summary: null, location_data: {} };
      }
      throw err;
    }
  },

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

  // ---------------- Memory ops ----------------

  newStore: (path: string) =>
    postJSON<{ success: boolean; path?: string; message?: string }>(
      "/api/new",
      { path },
    ),

  remember: (path: string, content: string, namespace = "default") =>
    postJSON<Record<string, unknown>>("/api/remember", {
      path,
      content,
      namespace,
    }),

  /**
   * Direct edit — bypasses the classifier and writes the supplied
   * content at exactly ``key``. ``editSource`` annotates the commit
   * message: "manual" (default), "llm" (the LLM rewrote it), or
   * "llm+manual" (LLM rewrote, user tweaked the result).
   */
  updateMemory: (
    path: string,
    key: string,
    content: string,
    opts: {
      namespace?: string;
      editSource?: "manual" | "llm" | "llm+manual";
      instructions?: string;
    } = {},
  ) =>
    postJSON<{
      success: boolean;
      key: string;
      namespace: string;
      commit_hash?: string;
      message?: string;
    }>("/api/update-memory", {
      path,
      key,
      content,
      namespace: opts.namespace ?? "default",
      edit_source: opts.editSource ?? "manual",
      instructions: opts.instructions ?? "",
    }),

  /**
   * Ask the LLM to rewrite content per natural-language instructions.
   * Returns the proposed new content without writing — caller loads
   * it into an editor and saves via ``updateMemory`` when ready.
   */
  rewriteMemory: (currentContent: string, instructions: string, key?: string) =>
    postJSON<{ success: boolean; new_content: string }>("/api/rewrite-memory", {
      current_content: currentContent,
      instructions,
      key: key ?? "",
    }),

  forget: (path: string, key: string, namespace = "default") =>
    postJSON<{ success: boolean; key: string; message?: string }>(
      "/api/forget",
      { path, key, namespace },
    ),

  recall: (path: string, query: string, mode: "single" | "tiered" = "single") =>
    getJSON<Record<string, unknown>>("/api/recall", { path, query, mode }),

  summarize: (
    path: string,
    opts: { type?: string; pattern?: string } = {},
  ) =>
    getJSON<Record<string, unknown>>("/api/summarize", {
      path,
      ...(opts.type ? { type: opts.type } : {}),
      ...(opts.pattern ? { pattern: opts.pattern } : {}),
    }),

  // ---------------- Crypto ----------------

  proof: (path: string, key: string, namespace = "default") =>
    getJSON<Record<string, unknown>>("/api/proof", { path, key, namespace }),

  verify: (path: string, key: string, proof: string, namespace = "default") =>
    getJSON<Record<string, unknown>>("/api/verify", {
      path,
      key,
      proof,
      namespace,
    }),

  blame: (path: string, key: string, namespace = "default") =>
    getJSON<Record<string, unknown>>("/api/blame", { path, key, namespace }),

  // ---------------- Branch ops ----------------

  checkout: (path: string, target: string, createBranch?: string) =>
    postJSON<{ success: boolean; message: string; current_branch: string }>(
      "/api/checkout",
      { path, target, create_branch: createBranch },
    ),

  createBranch: (path: string, branch: string, from = "HEAD") =>
    postJSON<{ success: boolean; message: string; branch: string }>(
      "/api/create-branch",
      { path, branch, from },
    ),

  deleteBranch: (path: string, branch: string) =>
    postJSON<{ success: boolean; message?: string }>("/api/delete-branch", {
      path,
      branch,
    }),

  mergeBranch: (path: string, source: string) =>
    postJSON<{ success: boolean; message?: string; conflict?: boolean }>(
      "/api/merge-branch",
      { path, source },
    ),
};
