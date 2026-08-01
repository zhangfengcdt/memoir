import { useMemo, useState } from "react";
import type { ChangeType, Memory } from "../../api/types";
import { buildTaxonomy, type TreeNode } from "../tree/buildTaxonomy";
import { assignCategoryColors, categoryOf, OTHER_CATEGORY_COLOR } from "../../lib/category";
import "./CategoryTree.css";

interface CategoryTreeProps {
  /** The full taxonomy state as of the commit being viewed (not just what
   * that commit changed) — see HistoryView's `asOf` accumulation. Leaf
   * paths present here but absent from `changedPaths` render a "kept"
   * badge, distinguishing "existed before this commit and is unchanged"
   * from "this commit touched it". */
  memories: Memory[];
  /** path → change type, for the currently selected commit. Leaf nodes
   * with an entry get a highlighted row + a +/~/− badge on top of their
   * category color; leaf nodes without one (but present in `memories`)
   * get a neutral "kept" badge instead. */
  changedPaths: Map<string, ChangeType>;
  /** The full set of categories to base color assignment on. Callers
   * should pass a stable, broad set (e.g. every category in the current
   * branch's taxonomy) rather than just `memories`' own categories —
   * `assignCategoryColors` ranks categories alphabetically to pick palette
   * slots, so if the input set changes with every render (as it would if
   * derived from `memories` alone while `memories` is just one commit's
   * changed paths), the same category can be reassigned a different color
   * from one commit selection to the next. Falls back to `memories`' own
   * categories when omitted. */
  paletteCategories?: Iterable<string>;
}

export default function CategoryTree({
  memories,
  changedPaths,
  paletteCategories,
}: CategoryTreeProps) {
  const namespaceTrees = useMemo(() => buildTaxonomy(memories), [memories]);

  const categoryColors = useMemo(() => {
    if (paletteCategories) return assignCategoryColors(paletteCategories);
    const cats: string[] = [];
    for (const ns of namespaceTrees) {
      for (const child of ns.root.children) cats.push(categoryOf(child.fullPath));
    }
    return assignCategoryColors(cats);
  }, [namespaceTrees, paletteCategories]);

  if (memories.length === 0) {
    return <p className="drawer-empty-hint">Nothing to show.</p>;
  }

  return (
    <div className="category-tree">
      <div className="category-tree-legend" aria-label="Category legend">
        {Array.from(categoryColors.entries()).map(([cat, color]) => (
          <span key={cat} className="category-legend-item">
            <span
              className="category-legend-dot"
              style={{ background: color }}
              aria-hidden="true"
            />
            {cat}
          </span>
        ))}
      </div>
      {namespaceTrees.map((ns) => (
        <div key={ns.namespace} className="category-tree-namespace">
          <div className="tree-namespace-header">
            <code className="tree-namespace-name">{ns.namespace}</code>
            <span className="tree-namespace-count">{ns.count}</span>
          </div>
          <ul className="category-tree-list">
            {ns.root.children.map((child) => (
              <CategoryNode
                key={child.fullPath}
                node={child}
                depth={0}
                color={
                  categoryColors.get(categoryOf(child.fullPath)) ??
                  OTHER_CATEGORY_COLOR
                }
                changedPaths={changedPaths}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

interface CategoryNodeProps {
  node: TreeNode;
  depth: number;
  color: string;
  changedPaths: Map<string, ChangeType>;
}

function CategoryNode({ node, depth, color, changedPaths }: CategoryNodeProps) {
  const [expanded, setExpanded] = useState(depth < 2);
  const changeType = changedPaths.get(node.fullPath);
  const hasChildren = node.children.length > 0;
  const isLeaf = node.directMemories.length > 0;
  // Existed as of this commit but wasn't touched by it — distinct from
  // the +/~/− badges, which mark what *this* commit changed.
  const kept = !changeType && isLeaf;
  const symbol = changeType === "added" ? "+" : changeType === "deleted" ? "−" : "~";

  return (
    <li className="category-node">
      <div
        className={`category-node-row${changeType ? ` changed type-${changeType}` : ""}`}
        style={{ paddingLeft: `${depth * 14}px`, ["--node-color" as string]: color }}
        onClick={hasChildren ? () => setExpanded((e) => !e) : undefined}
        role={hasChildren ? "button" : undefined}
        tabIndex={hasChildren ? 0 : undefined}
        onKeyDown={
          hasChildren
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setExpanded((v) => !v);
                }
              }
            : undefined
        }
      >
        {hasChildren ? (
          <span className="category-node-toggle" aria-hidden="true">
            {expanded ? "▾" : "▸"}
          </span>
        ) : (
          <span className="category-node-toggle" aria-hidden="true" />
        )}
        <span className="category-node-swatch" aria-hidden="true" />
        <span className="category-node-name">{node.name}</span>
        {changeType && (
          <span className={`category-node-badge tag-${changeType}`} title={changeType}>
            {symbol}
          </span>
        )}
        {kept && (
          <span className="category-node-badge tag-kept" title="unchanged by this commit">
            =
          </span>
        )}
        <span className="category-node-count">{node.count}</span>
      </div>
      {hasChildren && expanded && (
        <ul className="category-tree-list category-tree-children">
          {node.children.map((c) => (
            <CategoryNode
              key={c.fullPath}
              node={c}
              depth={depth + 1}
              color={color}
              changedPaths={changedPaths}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
