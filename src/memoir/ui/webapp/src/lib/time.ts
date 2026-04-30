/**
 * Render a unix-seconds timestamp as a short relative time, e.g.
 * "2m ago", "3h ago", "yesterday", "Apr 14". Mirrors how GitHub's commit
 * list reads — precise for recent activity, calendar-style for older.
 *
 * `now` is injectable for deterministic tests.
 */
export function relativeTime(unixSeconds: number, now: Date = new Date()): string {
  const then = new Date(unixSeconds * 1000);
  const diffMs = now.getTime() - then.getTime();
  const diffSec = Math.round(diffMs / 1000);

  if (Number.isNaN(diffSec)) return "—";
  if (diffSec < 45) return "just now";
  if (diffSec < 90) return "1m ago";

  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;

  const diffDay = Math.round(diffHr / 24);
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return `${diffDay}d ago`;
  if (diffDay < 14) return "1w ago";
  if (diffDay < 30) return `${Math.round(diffDay / 7)}w ago`;

  // Same year — month+day. Different year — include year.
  const sameYear = now.getFullYear() === then.getFullYear();
  return then.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
}

/**
 * Absolute ISO-like format for tooltips.
 */
export function absoluteTime(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Relative time from an ISO 8601 string (or any string ``Date.parse``
 * understands). Falls back to ``"—"`` for invalid input.
 */
export function relativeTimeFromISO(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "—";
  return relativeTime(Math.floor(ms / 1000), now);
}
