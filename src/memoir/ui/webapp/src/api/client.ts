import type {
  ApiError,
  BlameResponse,
  BranchesResponse,
  BranchesStatusResponse,
  BranchMergePreviewResponse,
  CommitsResponse,
  CurrentBranchResponse,
  LocationResponse,
  MetricsResponse,
  OnboardResponse,
  ProjectOnboardResponse,
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

  branchesStatus: (path: string) =>
    getJSON<BranchesStatusResponse>("/api/branches-status", { path }),

  /** Promote ``source``'s default-namespace memories into ``target``
   * (default ``main``). Pass ``{ dryRun: true }`` for a preview that
   * lists what would be added/updated without writing; pass
   * ``{ confirm: true }`` to actually apply. The server refuses to write
   * unless ``confirm`` is set, mirroring the delete-confirm flow. */
  syncBranch: (
    path: string,
    source: string,
    target: string,
    opts: { dryRun?: boolean; confirm?: boolean; excludedKeys?: string[] } = {},
  ) =>
    postJSON<{
      success: boolean;
      message?: string;
      added_keys?: string[];
      updated_keys?: string[];
      dry_run?: boolean;
      commit_hash?: string | null;
    }>("/api/sync-branches", {
      path,
      source,
      target,
      ...(opts.dryRun ? { dry_run: true } : {}),
      ...(opts.confirm ? { confirm: true } : {}),
      ...(opts.excludedKeys && opts.excludedKeys.length > 0
        ? { excluded_keys: opts.excludedKeys }
        : {}),
    }),

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

  onboard: (path: string) =>
    getJSON<OnboardResponse>("/api/onboard", { path }),

  projectOnboard: (path: string) =>
    getJSON<ProjectOnboardResponse>("/api/project-onboard", { path }),

  metrics: (path: string) =>
    getJSON<MetricsResponse>("/api/metrics", { path }),

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

  /** Flat-by-key preview of what ``promote_branch(to → from)`` would carry,
   * with BEFORE/AFTER content. Same semantics as the merge confirmation
   * panel — added/modified only, default namespace only, deletions skipped. */
  branchMergePreview: (
    path: string,
    fromRef: string,
    toRef: string,
  ): Promise<BranchMergePreviewResponse> =>
    getJSON<BranchMergePreviewResponse>("/api/branch-merge-preview", {
      path,
      from: fromRef,
      to: toRef,
    }),

  // ---------------- Memory ops ----------------
  //
  // Note: store creation has no client method. It is intentionally CLI-only
  // (`memoir new <path>`) so the UI can't accidentally land an "Initial
  // commit" in an unrelated git repo when a path resolves wrong.

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
    getJSON<BlameResponse>("/api/blame", { path, key, namespace }),

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

  /**
   * Delete a memoir branch. Defaults to ``force: true`` because memoir's
   * "merged" semantics use the sync marker, not git ancestry — so a
   * branch can be sync'd into main and still appear "not fully merged"
   * to git, which would otherwise block the delete.
   */
  deleteBranch: (path: string, branch: string, opts: { force?: boolean } = {}) =>
    postJSON<{ success: boolean; message?: string }>("/api/delete-branch", {
      path,
      branch,
      force: opts.force ?? true,
    }),

  mergeBranch: (path: string, source: string) =>
    postJSON<{ success: boolean; message?: string; conflict?: boolean }>(
      "/api/merge-branch",
      { path, source },
    ),

  // ---------- Watch / Search ---------------------------------------------

  watchList: (path: string) =>
    getJSON<WatchListResponse>("/api/watch/list", { path }),

  watchFiles: (path: string, watched: string) =>
    getJSON<WatchFilesResponse>("/api/watch/files", { path, watched }),

  /** Kick off indexing in the background. Returns 202 with `indexing: true`;
   * the row will keep `indexing: true` in subsequent /api/watch/list polls
   * until the server-side thread completes. */
  watchAddPath: (
    store: string,
    file: string,
    opts: { namespace?: string; model?: string } = {},
  ) =>
    postJSON<{
      success: boolean;
      path: string;
      indexing: boolean;
      already_in_flight?: boolean;
      error?: string;
    }>("/api/watch/add", {
      store,
      file,
      namespace: opts.namespace ?? "watch",
      ...(opts.model ? { model: opts.model } : {}),
    }),

  /** Unregister a watched file and purge every ``raw.<file>.*`` key from
   * both the KV store and the vector index. The server's remove() always
   * cleans up; the legacy ``--purge`` flag is no-op. */
  watchRemovePath: (store: string, file: string) =>
    postJSON<{
      success: boolean;
      path: string;
      files_removed: number;
      purge: boolean;
      error?: string;
    }>("/api/watch/remove", { store, file }),

  /** Re-scan a registered watched file in the background. Same async
   * semantics as ``watchAddPath``: returns 202 with ``indexing: true``;
   * the row shows the indexing badge until the server's background
   * thread completes (or fails). */
  watchScanPath: (
    store: string,
    file: string,
    opts: { namespace?: string; model?: string } = {},
  ) =>
    postJSON<{
      success: boolean;
      path: string;
      indexing: boolean;
      already_in_flight?: boolean;
      error?: string;
    }>("/api/watch/scan", {
      store,
      file,
      namespace: opts.namespace ?? "watch",
      ...(opts.model ? { model: opts.model } : {}),
    }),

  /** Re-scan every registered watched file in the background, one at a
   * time. Each file's row lights up the ``indexing…`` badge while
   * being processed; the polling effect in WatchView covers the
   * progression. */
  watchScanAll: (store: string, opts: { model?: string } = {}) =>
    postJSON<{
      success: boolean;
      scheduled: number;
      paths: string[];
      indexing: boolean;
      error?: string;
    }>("/api/watch/scan-all", {
      store,
      ...(opts.model ? { model: opts.model } : {}),
    }),

  watchSearch: (
    path: string,
    query: string,
    opts: { namespace?: string; k?: number } = {},
  ) =>
    getJSON<WatchSearchResponse>("/api/watch/search", {
      path,
      query,
      namespace: opts.namespace ?? "default",
      k: String(opts.k ?? 5),
    }),
};

// ---------- Watch / Search response types --------------------------------

export interface WatchEntry {
  path: string;
  kind: string; // "file" | "folder"
  namespace: string;
  added_at: string;
  last_scan: string | null;
  indexed_count: number;
  /** Transient flag set by the UI server while a background-thread
   *  index is in progress. Cleared once indexing finishes. */
  indexing?: boolean;
  /** Set when the background thread raised; the badge stays "failed" for
   *  ~30s then disappears so the user can retry. */
  indexing_error?: string | null;
}

export interface WatchListResponse {
  success: boolean;
  entries: WatchEntry[];
  count: number;
  error: string | null;
}

export interface WatchFile {
  abs_path: string;
  size: number;
  indexed_at: string;
  mtime: number | null;
  summary_chars: number;
  content_hash: string;
}

export interface WatchFilesResponse {
  success: boolean;
  watched_path: string;
  files: WatchFile[];
  count: number;
  error: string | null;
}

export interface WatchSearchHit {
  key: string;
  score: number;
  content: string;
  namespace: string;
  source: { kind?: string; abs_path?: string } | null;
  related_keys: string[];
}

export interface WatchSearchResponse {
  success: boolean;
  query: string;
  hits: WatchSearchHit[];
  count: number;
  namespace: string;
  timing_ms: number;
  error: string | null;
}
