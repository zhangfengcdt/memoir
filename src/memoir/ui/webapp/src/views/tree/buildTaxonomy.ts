import type { Memory } from "../../api/types";

/**
 * Node in a taxonomy tree.
 *
 * Internal nodes carry ``count`` (total memories in their subtree).
 * Leaf / exact-match memories sit in ``directMemories`` — a single
 * semantic path can hold more than one memory in practice (same key
 * updated over time with different values), though typically it's 0
 * for internal paths and 1 for leaves.
 */
export interface TreeNode {
  /** Last segment of the dotted path, e.g. "style" for "workflow.coding.style". */
  name: string;
  /** Full dotted path within the namespace, e.g. "workflow.coding.style". */
  fullPath: string;
  /** Memories whose path ends exactly at this node. */
  directMemories: Memory[];
  /** Total memories under this subtree (direct + all descendants). */
  count: number;
  /** Child nodes, sorted alphabetically by name. */
  children: TreeNode[];
}

/**
 * One namespace plus its taxonomy tree.
 */
export interface NamespaceTree {
  namespace: string;
  count: number;
  root: TreeNode;
}

/**
 * Turn the flat memory list from ``GET /api/store`` into one tree per
 * namespace.
 *
 * Empty segments (e.g. ``workflow..style``) collapse to a synthetic
 * ``<empty>`` name so they don't produce invisible nodes.
 */
export function buildTaxonomy(memories: Memory[]): NamespaceTree[] {
  const byNamespace = new Map<string, Memory[]>();
  for (const m of memories) {
    const arr = byNamespace.get(m.namespace) ?? [];
    arr.push(m);
    byNamespace.set(m.namespace, arr);
  }

  const result: NamespaceTree[] = [];
  const sortedNamespaces = Array.from(byNamespace.keys()).sort();
  for (const namespace of sortedNamespaces) {
    const mems = byNamespace.get(namespace)!;
    result.push({
      namespace,
      count: mems.length,
      root: buildOneTree(mems),
    });
  }
  return result;
}

function buildOneTree(memories: Memory[]): TreeNode {
  const root: TreeNode = {
    name: "",
    fullPath: "",
    directMemories: [],
    count: memories.length,
    children: [],
  };

  for (const mem of memories) {
    const segments = mem.path
      .split(".")
      .map((s) => (s.length === 0 ? "<empty>" : s));
    let cursor = root;
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      const fullPath = segments.slice(0, i + 1).join(".");
      let child = cursor.children.find((c) => c.name === seg);
      if (!child) {
        child = {
          name: seg,
          fullPath,
          directMemories: [],
          count: 0,
          children: [],
        };
        cursor.children.push(child);
      }
      child.count++;
      if (i === segments.length - 1) {
        child.directMemories.push(mem);
      }
      cursor = child;
    }
  }

  sortRecursive(root);
  return root;
}

function sortRecursive(node: TreeNode): void {
  node.children.sort((a, b) => a.name.localeCompare(b.name));
  for (const c of node.children) sortRecursive(c);
}

/**
 * Traverse every node depth-first. Useful for flattening into a virtual
 * list or applying a side-effecting filter.
 */
export function walkTree(
  node: TreeNode,
  visit: (node: TreeNode, depth: number) => void,
  depth: number = 0,
): void {
  visit(node, depth);
  for (const c of node.children) walkTree(c, visit, depth + 1);
}
