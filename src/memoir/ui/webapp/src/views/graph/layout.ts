import type { Commit } from "../../api/types";

/**
 * Positioning data per commit for whichever graph layout is active.
 *
 * ``force`` mode leaves x/y undefined — d3-force computes them.
 * ``chronological`` mode fills them in so nodes sit on a grid where
 * x is time and y is a branch lane.
 */
export interface Placed {
  hash: string;
  /** Null in force mode, numeric in chronological mode. */
  x: number | null;
  /** Null in force mode, numeric in chronological mode. */
  y: number | null;
  /** Lane index (0, 1, 2, …) — stable across layouts for consistent coloring. */
  lane: number;
}

/**
 * Assign lanes to commits so branches get their own row in the
 * chronological layout.
 *
 * Strategy:
 * - Commits are processed newest-first (the order ``/api/commits`` returns).
 * - The HEAD (first commit in list) claims lane 0.
 * - For each subsequent commit, we pick the lowest-numbered lane whose
 *   current occupant has this commit as a parent. This "slot reuse"
 *   matches how ``git log --graph`` flows branches back into a single
 *   lane once they merge.
 * - If no lane can be reused, a new lane opens.
 * - Merge commits (>1 parent) mark all parent hashes as "reusable on
 *   their respective lanes" so non-first-parent branches get their own row.
 *
 * Returns a map from commit hash → Placed.
 */
export function assignLanes(commits: Commit[]): Map<string, Placed> {
  // hashByParent tracks, for each lane, which commit-hash is currently
  // "waiting" for that hash to appear — when we process a commit matching
  // the waiting hash, the lane is reused.
  const laneExpects: (string | null)[] = []; // index → parent-hash that would reuse this lane
  const placed = new Map<string, Placed>();

  for (const commit of commits) {
    // Try to reuse a lane whose expected hash matches this commit.
    let lane = laneExpects.findIndex((h) => h === commit.hash);
    if (lane < 0) {
      // Open a new lane.
      lane = laneExpects.length;
      laneExpects.push(null);
    }

    placed.set(commit.hash, {
      hash: commit.hash,
      x: null,
      y: null,
      lane,
    });

    // This lane now expects the commit's first parent.
    laneExpects[lane] = commit.parents[0] ?? null;

    // For merges, give each non-first parent its own lane (opening a new
    // one if none match).
    for (let i = 1; i < commit.parents.length; i++) {
      const parent = commit.parents[i];
      const existing = laneExpects.indexOf(parent);
      if (existing < 0) {
        laneExpects.push(parent);
      }
    }
  }

  return placed;
}

interface ChronoOptions {
  width: number;
  height: number;
  marginX?: number;
  marginY?: number;
  laneSpacing?: number;
}

/**
 * Fill in ``x`` (by timestamp) and ``y`` (by lane) on a `Placed` map
 * so the graph lays out chronologically.
 *
 * Timestamps are linearly mapped to ``[marginX, width - marginX]``. If
 * all commits share a timestamp, they share an x and get visually
 * stacked — caller can zoom / pan to resolve.
 */
export function chronologicalPositions(
  commits: Commit[],
  placed: Map<string, Placed>,
  { width, height, marginX = 48, marginY = 48, laneSpacing = 48 }: ChronoOptions,
): Map<string, Placed> {
  if (commits.length === 0) return placed;
  const timestamps = commits.map((c) => c.timestamp);
  const minT = Math.min(...timestamps);
  const maxT = Math.max(...timestamps);
  const span = maxT - minT || 1;

  const out = new Map<string, Placed>();
  for (const commit of commits) {
    const p = placed.get(commit.hash);
    if (!p) continue;
    const x =
      marginX +
      ((commit.timestamp - minT) / span) * (width - 2 * marginX);
    const y = Math.min(
      height - marginY,
      marginY + p.lane * laneSpacing,
    );
    out.set(commit.hash, { ...p, x, y });
  }
  return out;
}
