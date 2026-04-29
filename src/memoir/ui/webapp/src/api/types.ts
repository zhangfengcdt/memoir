// ⚠ Hand-maintained mirror of `src/memoir/ui/schemas/` (Pydantic).
// Keep this file in sync with the Python models until OpenAPI codegen
// lands. The handler unit tests assert the real wire shape matches
// Pydantic — if those tests pass but the UI breaks, suspect this file.

export interface ApiError {
  error: string;
  status: number;
}

// --- /api/store ------------------------------------------------------------
// Pydantic: StoreResponse (extra='allow')
export interface StoreCommit {
  hash: string;
  message: string;
}

// Pydantic: Memory (extra='allow')
export interface Memory {
  key: string;       // "namespace:path"
  namespace: string; // e.g. "default", "codebase:onboard"
  path: string;      // e.g. "workflow.coding.style"
  content: string | null;
  value: Record<string, unknown>;
}

export interface StoreResponse {
  store_path: string;
  branches: string[];
  current_branch: string;
  commits: StoreCommit[];
  namespaces: Record<string, string[]>;
  memories: Memory[];
  total_memories: number;
  // legacy extras preserved on the wire:
  tree?: Record<string, number>;
}

// --- /api/branches ---------------------------------------------------------
export interface BranchesResponse {
  success: boolean;
  branches: string[];
  current: string;
}

// --- /api/branches-status --------------------------------------------------
export interface BranchStatus {
  name: string;
  is_default: boolean;
  is_current: boolean;
  ahead: number;
  behind: number;
  /** Number of default-namespace keys (additions + modifications) that would
   * sync to the default branch via promote_branch. This is the count the
   * "↑ N ahead" pill displays — reflects what would actually merge, not
   * the raw commit count. Servers older than this field default to 0. */
  keys_ahead?: number;
  last_commit_date: string | null;
  synced: boolean;
}

export interface BranchesStatusResponse {
  success: boolean;
  default: string;
  current: string;
  branches: BranchStatus[];
}

// --- /api/current-branch ---------------------------------------------------
export interface CurrentBranchResponse {
  success: boolean;
  branch: string;
  commit: string;
}

// --- /api/statistics -------------------------------------------------------
export type StatsSection = Record<string, unknown>;

export interface StatisticsBlock {
  storage: StatsSection;
  tree_structure: StatsSection;
  versioning: StatsSection;
  metadata: StatsSection;
  performance: StatsSection;
  taxonomy: StatsSection;
  content: StatsSection;
  system: StatsSection;
}

export interface StatisticsResponse {
  success: boolean;
  statistics: StatisticsBlock;
  generated_at: string;
  store_path: string;
}

// --- /api/onboard ----------------------------------------------------------
// Raw read of the codebase:onboard namespace. No LLM. The UI groups items
// by L1 prefix (root before the first dot) for the Stats > Onboard tab.
export interface OnboardItem {
  key: string;
  value: unknown;
}

export interface OnboardResponse {
  success: boolean;
  items: OnboardItem[];
  /** Best-effort path to the code repo this snapshot was taken against.
   * Null if the server couldn't resolve it. */
  code_repo_path?: string | null;
  /** Current `git rev-parse HEAD` of the code repo. Null on failure. */
  current_code_commit?: string | null;
  /** Current code branch name. Null on failure. */
  current_code_branch?: string | null;
}

// --- /api/project-onboard --------------------------------------------------
// Raw read of the project:onboard namespace (the non-git counterpart of
// codebase:onboard). Same item shape as OnboardItem; no code-repo fields,
// since non-git folders have no code commit/branch to compare against.
// Staleness is signaled via _meta.last_onboard.snapshot_hash + date.
export type ProjectOnboardItem = OnboardItem;

export interface ProjectOnboardResponse {
  success: boolean;
  items: ProjectOnboardItem[];
}

// --- /api/metrics ----------------------------------------------------------
// All `metrics.*` keys in the default namespace on the current branch.
// `branch` is parsed out of the key fragment for `metrics.turn.<branch>` —
// null for any other shape so future metrics roots can ride along.
export interface MetricsItem {
  key: string;
  branch: string | null;
  value: Record<string, unknown> | unknown;
}

export interface MetricsResponse {
  success: boolean;
  items: MetricsItem[];
}

// --- /api/timeline ---------------------------------------------------------
export interface TimelineResponse {
  success: boolean;
  summary: string | null;
  /** YYYYMMDD → event text */
  timeline_data: Record<string, string>;
  start_date: string | null;
  end_date: string | null;
}

// --- /api/location ---------------------------------------------------------
export interface Place {
  name: string;
  content: string;
}

export interface LocationResponse {
  success: boolean;
  summary: string | null;
  /** slug → place */
  location_data: Record<string, Place>;
}

// --- /api/commit-range-diff -----------------------------------------------
export type ChangeType = "added" | "deleted" | "modified";

export interface Change {
  path: string;
  type: ChangeType;
  old_content?: string | null;
  new_content?: string | null;
}

export interface ChangeStats {
  added: number;
  modified: number;
  deleted: number;
}

export interface CommitDiff {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  email: string;
  timestamp: number;
  changes: Change[];
  stats: ChangeStats;
}

// Wire-native keys are `from` and `to`; both are JS reserved-ish and
// collide with TS keywords in destructuring. The client normalizes them
// to `fromRef` / `toRef` before this shape ever hits UI code.
export interface RangeDiffResponse {
  success: boolean;
  fromRef: string;
  toRef: string;
  commits: CommitDiff[];
}

// --- /api/branch-merge-preview --------------------------------------------
// Flat-by-key view of what ``promote_branch(to → from)`` would carry.
// Backs BranchCommitsModal — renders the same add/update operations the
// merge confirmation panel shows, plus BEFORE/AFTER content.
export interface MergePreviewAdded {
  path: string;
  new_content: string;
}

export interface MergePreviewModified {
  path: string;
  old_content: string;
  new_content: string;
}

export interface BranchMergePreviewResponse {
  success: boolean;
  from: string;
  to: string;
  added: MergePreviewAdded[];
  modified: MergePreviewModified[];
  error?: string;
}

// --- /api/commits ----------------------------------------------------------
export interface Commit {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  email: string;
  timestamp: number; // unix seconds
  // Full parent hashes. First = canonical ancestor; more than one means
  // this was a merge commit. Empty for the initial commit.
  parents: string[];
  // Tag names pointing at this commit (no `refs/tags/` prefix).
  tags: string[];
  // Branch-head names pointing at this commit (no `refs/heads/` prefix).
  refs: string[];
}

export interface CommitsResponse {
  success: boolean;
  commits: Commit[];
  branch: string;
}

// --- /api/blame ------------------------------------------------------------
// Pydantic-shaped via BlameEntry.to_dict() in services/models.py.
export interface BlameEntry {
  commit: string; // 8-char short SHA, "unknown" if missing
  author: string; // "Name <email>" or "Unknown"
  date: string; // ISO 8601, may be empty
  message: string;
}

export interface BlameResponse {
  success: boolean;
  key: string;
  namespace: string;
  entries: BlameEntry[];
}
