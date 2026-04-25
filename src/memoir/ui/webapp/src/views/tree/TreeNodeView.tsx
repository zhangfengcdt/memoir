import { KeyboardEvent, memo } from "react";
import type { Memory } from "../../api/types";
import type { TreeNode } from "./buildTaxonomy";

interface TreeNodeViewProps {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  selectedKey: string | null;
  onToggle: (fullPath: string) => void;
  onPickMemory: (memory: Memory) => void;
}

/**
 * Recursive renderer for one taxonomy node and its children.
 *
 * ``memo`` keeps unrelated subtrees from re-rendering when the user
 * expands a sibling — the parent passes stable `expanded` / `selectedKey`
 * sets, so React's shallow compare is enough.
 */
function TreeNodeViewInner({
  node,
  depth,
  expanded,
  selectedKey,
  onToggle,
  onPickMemory,
}: TreeNodeViewProps) {
  const hasChildren = node.children.length > 0;
  const hasDirectMemories = node.directMemories.length > 0;
  const isExpanded = expanded.has(node.fullPath);
  // A "terminal" row holds a memory at exactly this path with no
  // children below it. Clicking it should jump straight into the
  // memory drawer rather than expanding (there's nothing to expand).
  const isTerminal = !hasChildren && hasDirectMemories;
  const isSelected = isTerminal && selectedKey === node.directMemories[0].key;

  const handleActivate = () => {
    if (hasChildren) {
      onToggle(node.fullPath);
    } else if (hasDirectMemories) {
      onPickMemory(node.directMemories[0]);
    }
  };

  const onRowKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleActivate();
    } else if (e.key === "ArrowRight" && hasChildren && !isExpanded) {
      e.preventDefault();
      onToggle(node.fullPath);
    } else if (e.key === "ArrowLeft" && hasChildren && isExpanded) {
      e.preventDefault();
      onToggle(node.fullPath);
    }
  };

  // Build a tooltip showing the first line of content for terminal rows
  // so users get a preview without needing to expand or click.
  const terminalPreview = isTerminal
    ? (node.directMemories[0].content ?? "").split("\n")[0]
    : null;

  return (
    <li className="tree-node" data-depth={depth}>
      <button
        type="button"
        className={`tree-row${isTerminal ? " terminal" : ""}${isSelected ? " selected" : ""}`}
        onClick={handleActivate}
        onKeyDown={onRowKey}
        aria-expanded={hasChildren ? isExpanded : undefined}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        title={terminalPreview ?? undefined}
      >
        <span className="tree-caret" aria-hidden="true">
          {hasChildren ? (isExpanded ? "▾" : "▸") : isTerminal ? "•" : "·"}
        </span>
        <span className="tree-name">{node.name}</span>
        {isTerminal && terminalPreview && (
          <span className="tree-row-preview">{terminalPreview.slice(0, 80)}</span>
        )}
        <span className="tree-count">{node.count}</span>
      </button>

      {/*
       * Direct memories are rendered as MemoryLeaf rows ONLY when the
       * node also has children — otherwise the row itself IS the leaf
       * and clicking it opens the drawer (handled above).
       */}
      {isExpanded && hasChildren && hasDirectMemories && (
        <ul className="tree-memories">
          {node.directMemories.map((m) => (
            <MemoryLeaf
              key={m.key}
              memory={m}
              depth={depth + 1}
              selected={selectedKey === m.key}
              onPick={onPickMemory}
            />
          ))}
        </ul>
      )}

      {isExpanded && hasChildren && (
        <ul className="tree-children">
          {node.children.map((c) => (
            <TreeNodeView
              key={c.fullPath}
              node={c}
              depth={depth + 1}
              expanded={expanded}
              selectedKey={selectedKey}
              onToggle={onToggle}
              onPickMemory={onPickMemory}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

const TreeNodeView = memo(TreeNodeViewInner);
export default TreeNodeView;

interface MemoryLeafProps {
  memory: Memory;
  depth: number;
  selected: boolean;
  onPick: (memory: Memory) => void;
}

function MemoryLeaf({ memory, depth, selected, onPick }: MemoryLeafProps) {
  const preview = (memory.content ?? "").split("\n")[0].slice(0, 160);
  return (
    <li className="tree-leaf" data-depth={depth}>
      <button
        type="button"
        className={`tree-leaf-row${selected ? " selected" : ""}`}
        onClick={() => onPick(memory)}
        style={{ paddingLeft: `${depth * 14 + 22}px` }}
        title={memory.content ?? memory.key}
      >
        <span className="tree-leaf-dot" aria-hidden="true" />
        <code className="tree-leaf-path">{memory.path.split(".").pop()}</code>
        <span className="tree-leaf-preview">{preview}</span>
      </button>
    </li>
  );
}
