/**
 * Compile a search/glob pattern into a predicate.
 *
 * Wildcards in the pattern (anchored, full-string match):
 *   *   matches any sequence of characters (including dots)
 *   ?   matches exactly one character
 *
 * If the pattern contains no wildcards at all, it is treated as a
 * substring match — typing ``workflow`` matches any path containing
 * ``workflow``, not only the exact key ``workflow``. This matches the
 * mental model users have for a "Match" search box; explicit wildcards
 * (``workflow.*``, ``*.style``) opt back into glob semantics.
 *
 * Empty / whitespace-only patterns return ``null`` so callers can treat
 * them as "no filter" without a sentinel value. Match is
 * case-insensitive — taxonomy paths are lowercase by convention but the
 * user shouldn't be punished for typing ``Workflow``.
 */
export function compileWildcard(pattern: string): ((s: string) => boolean) | null {
  const trimmed = pattern.trim();
  if (!trimmed) return null;
  // Escape every regex metacharacter, including * and ?, then re-translate
  // the escaped wildcards back into regex equivalents. Doing it in two
  // steps avoids hand-rolled escape lists that miss edge characters.
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const hasWildcard = /[*?]/.test(trimmed);
  const body = escaped.replace(/\\\*/g, ".*").replace(/\\\?/g, ".");
  // No explicit wildcard → substring match. Otherwise anchored glob.
  const re = hasWildcard ? `^${body}$` : `.*${body}.*`;
  let regex: RegExp;
  try {
    regex = new RegExp(re, "i");
  } catch {
    return null;
  }
  return (s: string) => regex.test(s);
}
