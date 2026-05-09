import { useUI, DEPTH_OPTIONS, type DepthFilter } from "../state/uiSlice";
import "./FilterBar.css";

/**
 * Shared filter row mounted above the Outline (tree) and Map (graph)
 * views. Three controls:
 *
 *   - Match  — wildcard pattern (* / ?) that paths MUST match.
 *   - Exclude — wildcard pattern that paths MUST NOT match.
 *   - Depth   — All / L1 / L2 / L3, prunes the taxonomy at N segments.
 *
 * State lives on ``uiSlice`` so both views see the same filters and the
 * settings persist across reloads. Empty inputs disable that filter.
 */
export default function FilterBar() {
  const keyInclude = useUI((s) => s.keyInclude);
  const keyExclude = useUI((s) => s.keyExclude);
  const depthFilter = useUI((s) => s.depthFilter);
  const setKeyInclude = useUI((s) => s.setKeyInclude);
  const setKeyExclude = useUI((s) => s.setKeyExclude);
  const setDepthFilter = useUI((s) => s.setDepthFilter);
  const clearFilters = useUI((s) => s.clearFilters);

  const active =
    keyInclude.trim() !== "" ||
    keyExclude.trim() !== "" ||
    depthFilter !== "all";

  return (
    <div
      className="filter-bar"
      role="toolbar"
      aria-label="Outline and Map filters"
    >
      <label className="filter-bar-field">
        <span className="filter-bar-label">Match</span>
        <input
          type="text"
          className="filter-bar-input"
          placeholder="text or glob (e.g. workflow, *.style)"
          value={keyInclude}
          onChange={(e) => setKeyInclude(e.target.value)}
          spellCheck={false}
          autoComplete="off"
          title="Plain text matches as a substring. Use * or ? for glob: workflow.*, *.style, ??."
          aria-label="Pattern memory paths must match"
        />
      </label>

      <label className="filter-bar-field">
        <span className="filter-bar-label">Exclude</span>
        <input
          type="text"
          className="filter-bar-input"
          placeholder="text or glob (e.g. metrics, *.session)"
          value={keyExclude}
          onChange={(e) => setKeyExclude(e.target.value)}
          spellCheck={false}
          autoComplete="off"
          title="Plain text matches as a substring. Use * or ? for glob."
          aria-label="Pattern memory paths must not match"
        />
      </label>

      <div className="filter-bar-field filter-bar-depth">
        <span className="filter-bar-label">Depth</span>
        <div
          className="filter-bar-segmented"
          role="group"
          aria-label="Maximum taxonomy depth"
        >
          {DEPTH_OPTIONS.map((opt) => (
            <button
              key={String(opt)}
              type="button"
              className={`filter-bar-segment${
                depthFilter === opt ? " active" : ""
              }`}
              onClick={() => setDepthFilter(opt)}
              aria-pressed={depthFilter === opt}
              title={depthLabelLong(opt)}
            >
              {depthLabelShort(opt)}
            </button>
          ))}
        </div>
      </div>

      <button
        type="button"
        className="filter-bar-clear"
        onClick={clearFilters}
        disabled={!active}
        title="Clear all filters"
      >
        Clear
      </button>
    </div>
  );
}

function depthLabelShort(opt: DepthFilter): string {
  return opt === "all" ? "All" : `L${opt}`;
}

function depthLabelLong(opt: DepthFilter): string {
  return opt === "all"
    ? "Show every level"
    : `Show only the first ${opt} segment${opt === 1 ? "" : "s"}`;
}
