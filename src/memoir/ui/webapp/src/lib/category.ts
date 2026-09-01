import { splitTaxonomyPath } from "../views/tree/buildTaxonomy";

/**
 * Top-level taxonomy segment a path belongs to, e.g. "workflow" for
 * "workflow.coding.style". Taxonomy-agnostic — works for any path shape,
 * not just the fixed 8-value TaxonomyCategory enum the backend also
 * exposes (which many real paths, like the example above, fall outside
 * of). This is the same segmenting `buildTaxonomy`/`TaxonomyTree` already
 * use for grouping, just truncated to the first segment.
 */
export function categoryOf(path: string): string {
  return splitTaxonomyPath(path)[0] || "uncategorized";
}

/**
 * Fixed-order categorical hues, validated (dataviz skill's
 * `validate_palette.js`) against this app's dark surface (`--bg-1`,
 * `#10141c`): lightness band, chroma floor, CVD adjacent-pair separation,
 * normal-vision floor, and contrast all pass for the full 8-slot set.
 *
 * Per the skill's non-negotiable, hues are assigned in this fixed order
 * and never cycled/hashed past the cap — a 9th+ category folds into the
 * shared "other" muted color rather than generating a new hue.
 */
const CATEGORY_PALETTE: readonly string[] = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
];

/** Color for categories beyond the fixed palette's 8 slots. */
export const OTHER_CATEGORY_COLOR = "#6b7384"; // --fg-2

/**
 * Assign each distinct category a stable color, in a deterministic
 * (alphabetical) order so the same set of categories always maps the same
 * way across renders — without hashing, which the palette contract
 * forbids for slot assignment. Categories past the 8th share
 * `OTHER_CATEGORY_COLOR`.
 */
export function assignCategoryColors(
  categories: Iterable<string>,
): Map<string, string> {
  const unique = Array.from(new Set(categories)).sort((a, b) =>
    a.localeCompare(b),
  );
  const map = new Map<string, string>();
  unique.forEach((cat, i) => {
    map.set(
      cat,
      i < CATEGORY_PALETTE.length ? CATEGORY_PALETTE[i] : OTHER_CATEGORY_COLOR,
    );
  });
  return map;
}
