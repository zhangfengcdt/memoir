import { useCallback, useEffect, useMemo, useState } from "react";
import { useStore } from "../../state/storeSlice";
import { useMemorySelection } from "../../state/memorySelectionSlice";
import { useUI } from "../../state/uiSlice";
import { buildTaxonomy, walkTree } from "./buildTaxonomy";
import type { Memory } from "../../api/types";
import TreeNodeView from "./TreeNodeView";
import "./TaxonomyTree.css";

export default function TaxonomyTree() {
  const allMemories = useStore((s) => s.data?.memories ?? []);
  const selected = useMemorySelection((s) => s.selected);
  const select = useMemorySelection((s) => s.select);
  const selectedNamespace = useUI((s) => s.selectedNamespace);

  // When the user has clicked a namespace in the LeftPane, hide the
  // others. Null = "All namespaces" (the default).
  const memories = useMemo(
    () =>
      selectedNamespace
        ? allMemories.filter((m) => m.namespace === selectedNamespace)
        : allMemories,
    [allMemories, selectedNamespace],
  );

  const namespaces = useMemo(() => buildTaxonomy(memories), [memories]);

  // Expansion state, keyed by "<namespace>:<fullPath>". Two namespaces
  // can legitimately share a prefix (e.g. both have "workflow"), so we
  // qualify with the namespace to keep expansion independent per tree.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  // On first load / whenever the memory set changes materially, auto-
  // expand the first two levels so users see something without clicking.
  useEffect(() => {
    const next = new Set<string>();
    for (const ns of namespaces) {
      walkTree(ns.root, (node, depth) => {
        if (depth > 0 && depth <= 2 && node.count > 0) {
          next.add(`${ns.namespace}:${node.fullPath}`);
        }
      });
    }
    setExpanded(next);
  }, [namespaces]);

  const toggle = useCallback(
    (qualifiedPath: string) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(qualifiedPath)) next.delete(qualifiedPath);
        else next.add(qualifiedPath);
        return next;
      });
    },
    [],
  );

  const onPickMemory = useCallback(
    (m: Memory) => {
      select(m);
      useUI.getState().pushPanel({ kind: "memory-detail", memory: m });
    },
    [select],
  );

  if (memories.length === 0) {
    if (selectedNamespace) {
      return (
        <div className="tree-empty">
          <p>
            No memories under <code>{selectedNamespace}</code>.
          </p>
          <p>
            Click <strong>All namespaces</strong> in the left pane to clear the
            filter, or run <code>/remember</code> to capture one.
          </p>
        </div>
      );
    }
    return (
      <div className="tree-empty">
        <p>No memories to taxonomise yet.</p>
        <p>
          Run <code>/remember &lt;text&gt;</code> from a session to capture some,
          then <code>/refresh</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="tree-wrapper">
      <div className="tree-header">
        <div className="tree-summary">
          <span>{memories.length} memories</span>
          <span className="tree-sep" aria-hidden="true">
            ·
          </span>
          <span>{namespaces.length} namespace{namespaces.length === 1 ? "" : "s"}</span>
          {selectedNamespace && (
            <>
              <span className="tree-sep" aria-hidden="true">
                ·
              </span>
              <span className="chip accent">filter: {selectedNamespace}</span>
            </>
          )}
          {selected && (
            <>
              <span className="tree-sep" aria-hidden="true">
                ·
              </span>
              <span className="chip accent">selected: {selected.path}</span>
            </>
          )}
        </div>
      </div>

      <div className="tree-list">
        {namespaces.map((ns) => {
          const adjustedToggle = (fullPath: string) => toggle(`${ns.namespace}:${fullPath}`);
          return (
            <section key={ns.namespace} className="tree-namespace">
              <div className="tree-namespace-header">
                <code className="tree-namespace-name">{ns.namespace}</code>
                <span className="tree-namespace-count">{ns.count}</span>
              </div>
              <ul className="tree-nodes">
                {ns.root.children.map((child) => (
                  <TreeNodeView
                    key={child.fullPath}
                    node={child}
                    depth={0}
                    expanded={namespaceExpansionView(expanded, ns.namespace)}
                    selectedKey={selected?.key ?? null}
                    onToggle={adjustedToggle}
                    onPickMemory={onPickMemory}
                  />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Expose only the paths relevant to one namespace to each TreeNodeView,
 * so `expanded.has(fullPath)` inside the recursive tree doesn't have to
 * know about the namespace prefix.
 */
function namespaceExpansionView(expanded: Set<string>, namespace: string): Set<string> {
  const prefix = `${namespace}:`;
  const filtered = new Set<string>();
  for (const key of expanded) {
    if (key.startsWith(prefix)) filtered.add(key.slice(prefix.length));
  }
  return filtered;
}
