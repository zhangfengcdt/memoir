import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import type { Memory } from "../../api/types";
import { useStore } from "../../state/storeSlice";
import { useUI } from "../../state/uiSlice";
import { useMemorySelection } from "../../state/memorySelectionSlice";
import { buildTaxonomy, walkTree, type TreeNode } from "../tree/buildTaxonomy";
import "./TaxonomyGraph.css";

/**
 * Force-directed graph of the taxonomy:
 *   - one node per dotted path (and per ancestor prefix)
 *   - one link per parent→child relationship
 *   - styling by depth (top-level = large/teal, mid = purple, leaf = red)
 *
 * Reuses ``buildTaxonomy`` so the structure matches the Tree view
 * exactly. Selection filter from the LeftPane applies here too.
 */

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  /** Full dotted path within its namespace, prefixed by namespace. */
  qualifiedPath: string;
  namespace: string;
  fullPath: string;
  /** Last segment (e.g. "style" for "workflow.coding.style"). */
  name: string;
  /** Hierarchy depth (0 = top-level segment within a namespace). */
  depth: number;
  /** Number of memories under this subtree. */
  count: number;
  /** Memories that live exactly at this path (used for click → drawer). */
  directMemories: Memory[];
  /** Whether this node has any children — informs color tier. */
  hasChildren: boolean;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
}

export default function TaxonomyGraph() {
  const allMemories = useStore((s) => s.data?.memories ?? []);
  const connected = useStore((s) => s.status === "connected");
  const namespaceFilter = useUI((s) => s.selectedNamespace);
  const select = useMemorySelection((s) => s.select);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hovered, setHovered] = useState<GraphNode | null>(null);

  const memories = useMemo(
    () =>
      namespaceFilter
        ? allMemories.filter((m) => m.namespace === namespaceFilter)
        : allMemories,
    [allMemories, namespaceFilter],
  );

  const { nodes, links } = useMemo(() => buildGraph(memories), [memories]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || nodes.length === 0) return;

    const width = svg.clientWidth || 800;
    const height = svg.clientHeight || 500;

    const root = d3.select(svg);
    root.selectAll("*").remove();

    const zoomG = root.append("g").attr("class", "zoom-layer");
    root.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 4])
        .on("zoom", (event) => zoomG.attr("transform", event.transform)),
    );

    const linkG = zoomG.append("g").attr("class", "tx-links");
    const nodeG = zoomG.append("g").attr("class", "tx-nodes");

    // Resolve link endpoints to node refs (d3-force mutates these in place
    // during the simulation).
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    const resolved: GraphLink[] = [];
    for (const l of links) {
      const source = nodeById.get(l.source as string);
      const target = nodeById.get(l.target as string);
      if (source && target) resolved.push({ source, target });
    }

    const linkSel = linkG
      .selectAll("line")
      .data(resolved)
      .enter()
      .append("line")
      .attr("class", "tx-link");

    const nodeSel = nodeG
      .selectAll<SVGGElement, GraphNode>("g.tx-node")
      .data(nodes, (d) => (d as GraphNode).id)
      .enter()
      .append("g")
      .attr("class", (d) => `tx-node tier-${tierFor(d)}`)
      .style("cursor", (d) => (d.directMemories.length > 0 ? "pointer" : "default"))
      .on("click", (_event, d) => {
        const memory = d.directMemories[0];
        if (memory) {
          select(memory);
          useUI.getState().pushPanel({ kind: "memory-detail", memory });
        }
      })
      .on("mouseenter", (_event, d) => setHovered(d))
      .on("mouseleave", () => setHovered(null));

    // Node circle — size scales with depth tier.
    nodeSel
      .append("circle")
      .attr("r", (d) => radiusFor(d))
      .attr("class", "tx-node-circle");

    // Top-tier nodes get the segment name inside the circle; lower tiers
    // get the full dotted path next to the node so labels read correctly
    // even when many leaves share a prefix.
    nodeSel
      .filter((d) => d.depth === 0)
      .append("text")
      .attr("class", "tx-node-label-inside")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("dy", 1)
      .text((d) => d.name);

    nodeSel
      .filter((d) => d.depth > 0)
      .append("text")
      .attr("class", "tx-node-label-outside")
      .attr("text-anchor", "start")
      .attr("dy", 4)
      .attr("dx", (d) => radiusFor(d) + 6)
      .text((d) => d.fullPath);

    // v1-style centered layout: tiered radial forces pull root nodes
    // tightly to the center, branch nodes onto a mid ring, and leaves
    // out to a periphery. The link force keeps parent-child pairs
    // visually adjacent; charge keeps the periphery from collapsing.
    const cx = width / 2;
    const cy = height / 2;
    // Radii sized as a fraction of the smaller axis so the layout
    // breathes correctly in narrow + wide windows.
    const span = Math.min(width, height) / 2;
    const ringByDepth = (d: number) =>
      d === 0 ? 0 : d === 1 ? span * 0.45 : span * 0.85;

    const simulation = d3
      .forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, GraphLink>(resolved)
          .id((d) => d.id)
          .distance((l) => {
            const a = (l.source as GraphNode).depth;
            const b = (l.target as GraphNode).depth;
            // Bigger gap when crossing the root→branch ring; tighter
            // when going branch→leaf so leaves hug their parent.
            return Math.max(a, b) === 1 ? 90 : 60;
          })
          .strength(0.4),
      )
      .force("charge", d3.forceManyBody<GraphNode>().strength(-260))
      // Pull each node toward its tier's ring around the center.
      .force(
        "radial",
        d3
          .forceRadial<GraphNode>((d) => ringByDepth(d.depth), cx, cy)
          .strength((d) => (d.depth === 0 ? 0.18 : 0.08)),
      )
      // Soft center for the whole graph so it doesn't drift.
      .force("x", d3.forceX<GraphNode>(cx).strength(0.02))
      .force("y", d3.forceY<GraphNode>(cy).strength(0.02))
      .force(
        "collide",
        d3
          .forceCollide<GraphNode>()
          .radius((d) => radiusFor(d) + 22)
          .strength(0.9),
      );

    simulation.on("tick", () => {
      linkSel
        .attr("x1", (d) => (d.source as GraphNode).x ?? 0)
        .attr("y1", (d) => (d.source as GraphNode).y ?? 0)
        .attr("x2", (d) => (d.target as GraphNode).x ?? 0)
        .attr("y2", (d) => (d.target as GraphNode).y ?? 0);
      nodeSel.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, links, select]);

  if (!connected) return null;

  if (nodes.length === 0) {
    return (
      <div className="tx-empty">
        <p>
          {namespaceFilter
            ? `No memories under ${namespaceFilter}.`
            : "No memories to graph yet."}
        </p>
        <p>
          Run <code>/remember &lt;text&gt;</code> from a session to capture some,
          then <code>/refresh</code>.
        </p>
      </div>
    );
  }

  const depthCount = nodes.reduce(
    (acc, n) => {
      const tier = tierFor(n);
      acc[tier] = (acc[tier] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <div className="tx-wrapper">
      <div className="tx-header">
        <div className="tx-meta">
          <span>
            {nodes.length} nodes · {links.length} edges
          </span>
          <span className="tx-sep" aria-hidden="true">
            ·
          </span>
          <span className="tx-legend">
            <Dot tier="root" />
            top-level ({depthCount.root ?? 0})
            <Dot tier="branch" />
            branch ({depthCount.branch ?? 0})
            <Dot tier="leaf" />
            leaf ({depthCount.leaf ?? 0})
          </span>
          {namespaceFilter && (
            <span className="chip accent">filter: {namespaceFilter}</span>
          )}
        </div>
      </div>
      <div className="tx-canvas-wrapper">
        <svg ref={svgRef} className="tx-canvas" role="img" aria-label="Taxonomy graph" />
        {hovered && (
          <div className="tx-tooltip" role="tooltip">
            <code className="tx-tooltip-path">
              {hovered.namespace}:{hovered.fullPath || "(root)"}
            </code>
            <span className="tx-tooltip-count">
              {hovered.count} memor{hovered.count === 1 ? "y" : "ies"} under this prefix
            </span>
            {hovered.directMemories[0] && (
              <span className="tx-tooltip-snippet">
                {(hovered.directMemories[0].content ?? "").split("\n")[0].slice(0, 120)}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ----------------------------- helpers -----------------------------

function buildGraph(memories: Memory[]): {
  nodes: GraphNode[];
  links: GraphLink[];
} {
  const namespaces = buildTaxonomy(memories);
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const seen = new Set<string>();

  for (const ns of namespaces) {
    walkTree(ns.root, (node, depth) => {
      // Skip the synthetic per-namespace root — its children are the
      // depth-0 nodes we want as the visual roots.
      if (depth === 0) return;
      const id = `${ns.namespace}:${node.fullPath}`;
      if (seen.has(id)) return;
      seen.add(id);
      nodes.push({
        id,
        qualifiedPath: id,
        namespace: ns.namespace,
        fullPath: node.fullPath,
        name: node.name,
        depth: depth - 1, // shift so segment "workflow" → depth 0
        count: node.count,
        directMemories: node.directMemories,
        hasChildren: node.children.length > 0,
      });
      for (const child of node.children) {
        const childId = `${ns.namespace}:${child.fullPath}`;
        links.push({ source: id, target: childId });
      }
    });
  }
  return { nodes, links };
}

function tierFor(node: { depth: number; hasChildren: boolean }): "root" | "branch" | "leaf" {
  if (node.depth === 0) return "root";
  if (node.hasChildren) return "branch";
  return "leaf";
}

function radiusFor(node: GraphNode): number {
  switch (tierFor(node)) {
    case "root":
      return 32;
    case "branch":
      return 18;
    case "leaf":
      return 9;
  }
}

function Dot({ tier }: { tier: "root" | "branch" | "leaf" }) {
  return <span className={`tx-legend-dot tier-${tier}`} aria-hidden="true" />;
}

// Re-export for downstream type consumers (none today, but keeps the
// barrel obvious).
export type { TreeNode };
