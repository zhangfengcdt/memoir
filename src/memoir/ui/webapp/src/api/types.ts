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

// --- /api/current-branch ---------------------------------------------------
export interface CurrentBranchResponse {
  success: boolean;
  branch: string;
  commit: string;
}

// --- /api/commits ----------------------------------------------------------
export interface Commit {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  email: string;
  timestamp: number; // unix seconds
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
