import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { api, MemoirApiError } from "../../api/client";
import type { Commit } from "../../api/types";
import { useStore } from "../../state/storeSlice";
import { useUI } from "../../state/uiSlice";
import { useSelection } from "../../state/selectionSlice";
import { assignLanes, chronologicalPositions } from "./layout";
import "./CommitGraph.css";

type LayoutMode = "force" | "chronological";

interface GraphNode extends d3.SimulationNodeDatum {
  hash: string;
  commit: Commit;
  lane: number;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
}

const LANE_COLORS = [
  "#00d68f", // accent — first lane
  "#5d47d3",
  "#ffb84d",
  "#ff6b6b",
  "#0ea5ff",
  "#e879f9",
  "#a3e635",
  "#fb923c",
];

function laneColor(lane: number): string {
  return LANE_COLORS[lane % LANE_COLORS.length];
}

export default function CommitGraph() {
  const storePath = useStore((s) => s.storePath);
  const connected = useStore((s) => s.status === "connected");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [commits, setCommits] = useState<Commit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<LayoutMode>("force");
  const [hovered, setHovered] = useState<Commit | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!storePath || !connected) {
      setCommits(null);
      return;
    }
    setLoading(true);
    setError(null);
    // Pull more commits than the list view — the graph gets more useful
    // the more history it shows. Still bounded for perf.
    api
      .commits(storePath, { limit: 200 })
      .then((res) => {
        if (cancelled) return;
        setCommits(res.commits);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof MemoirApiError ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, connected]);

  const laneMap = useMemo(() => (commits ? assignLanes(commits) : new Map()), [commits]);
  const maxLane = useMemo(() => {
    let m = 0;
    for (const p of laneMap.values()) m = Math.max(m, p.lane);
    return m;
  }, [laneMap]);

  // D3 effect — rebuild the simulation when commits or layout mode changes.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !commits || commits.length === 0) return;

    const width = svg.clientWidth || 800;
    const height = svg.clientHeight || 500;

    // Build nodes + links.
    const nodes: GraphNode[] = commits.map((commit) => ({
      hash: commit.hash,
      commit,
      lane: laneMap.get(commit.hash)?.lane ?? 0,
    }));

    const links: GraphLink[] = [];
    const byHash = new Map(nodes.map((n) => [n.hash, n]));
    for (const commit of commits) {
      for (const parent of commit.parents) {
        if (byHash.has(parent)) {
          links.push({ source: commit.hash, target: parent });
        }
      }
    }

    // Initial positions for chronological mode.
    if (mode === "chronological") {
      const placed = chronologicalPositions(commits, laneMap, {
        width,
        height,
      });
      for (const node of nodes) {
        const p = placed.get(node.hash);
        if (p) {
          node.fx = p.x ?? undefined;
          node.fy = p.y ?? undefined;
          node.x = p.x ?? undefined;
          node.y = p.y ?? undefined;
        }
      }
    } else {
      for (const node of nodes) {
        node.fx = undefined;
        node.fy = undefined;
      }
    }

    // Clear the SVG and set up a <g> for the zoom target.
    const root = d3.select(svg);
    root.selectAll("*").remove();

    const zoomG = root.append("g").attr("class", "zoom-layer");
    root.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 4])
        .on("zoom", (event) => {
          zoomG.attr("transform", event.transform);
        }),
    );

    const linkG = zoomG.append("g").attr("class", "links");
    const nodeG = zoomG.append("g").attr("class", "nodes");

    const linkSel = linkG
      .selectAll("line")
      .data(links)
      .enter()
      .append("line")
      .attr("class", "graph-link");

    const nodeSel = nodeG
      .selectAll<SVGGElement, GraphNode>("g.graph-node")
      .data(nodes, (d) => (d as GraphNode).hash)
      .enter()
      .append("g")
      .attr("class", "graph-node")
      .style("cursor", "pointer")
      .on("click", (_event, d) => {
        useSelection.getState().pick(d.hash);
        useUI
          .getState()
          .pushPanel({ kind: "commit-detail", commit: d.commit });
      })
      .on("mouseenter", (_event, d) => setHovered(d.commit))
      .on("mouseleave", () => setHovered(null));

    nodeSel
      .append("circle")
      .attr("r", 7)
      .attr("fill", (d) => laneColor(d.lane))
      .attr("stroke", "#0a0d12")
      .attr("stroke-width", 2);

    // Short hash label
    nodeSel
      .append("text")
      .attr("class", "graph-node-label")
      .attr("x", 12)
      .attr("y", 4)
      .text((d) => d.commit.short_hash);

    // Small chips for refs/tags (just dots with color; details live in the
    // drawer on click — keeps the graph readable at scale).
    nodeSel
      .filter((d) => d.commit.refs.length > 0)
      .append("circle")
      .attr("cx", -10)
      .attr("cy", 0)
      .attr("r", 3)
      .attr("fill", "#00ebaa");
    nodeSel
      .filter((d) => d.commit.tags.length > 0)
      .append("circle")
      .attr("cx", -10)
      .attr("cy", 8)
      .attr("r", 3)
      .attr("fill", "#ffb84d");

    // d3-force simulation. Chronological mode still runs a short sim so
    // the fixed x/y get "settled" into the DOM before being frozen.
    const simulation = d3
      .forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.hash)
          .distance(mode === "chronological" ? 0 : 56)
          .strength(mode === "chronological" ? 0 : 0.5),
      )
      .force(
        "charge",
        d3.forceManyBody<GraphNode>().strength(mode === "chronological" ? 0 : -180),
      )
      .force(
        "center",
        mode === "force" ? d3.forceCenter(width / 2, height / 2) : null,
      )
      .force(
        "x",
        mode === "chronological"
          ? null
          : d3.forceX<GraphNode>(width / 2).strength(0.02),
      )
      .force(
        "y",
        mode === "chronological"
          ? null
          : d3.forceY<GraphNode>(height / 2).strength(0.05),
      )
      .force(
        "collide",
        d3.forceCollide<GraphNode>().radius(14).strength(0.8),
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
  }, [commits, mode, laneMap]);

  if (!connected) return null;

  if (loading && commits === null) {
    return <div className="graph-empty">Loading commit graph…</div>;
  }

  if (error) {
    return (
      <div className="graph-empty graph-error">Failed to load graph: {error}</div>
    );
  }

  if (commits && commits.length === 0) {
    return (
      <div className="graph-empty">
        <p>No commits to graph yet.</p>
      </div>
    );
  }

  return (
    <div className="graph-wrapper">
      <div className="graph-header">
        <span className="eyebrow">Graph</span>
        <div className="graph-meta">
          <span>
            {commits?.length ?? 0} commits · {maxLane + 1} lane
            {maxLane + 1 === 1 ? "" : "s"}
          </span>
          <div className="graph-mode" role="tablist" aria-label="Layout mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "force"}
              className={`graph-mode-btn${mode === "force" ? " active" : ""}`}
              onClick={() => setMode("force")}
              title="Force-directed layout"
            >
              Force
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "chronological"}
              className={`graph-mode-btn${mode === "chronological" ? " active" : ""}`}
              onClick={() => setMode("chronological")}
              title="Chronological layout (x = time, y = branch)"
            >
              Chrono
            </button>
          </div>
        </div>
      </div>

      <div className="graph-canvas-wrapper">
        <svg ref={svgRef} className="graph-canvas" role="img" aria-label="Commit graph" />
        {hovered && (
          <div className="graph-tooltip" role="tooltip">
            <code className="graph-tooltip-hash">{hovered.short_hash}</code>
            <span className="graph-tooltip-msg">{hovered.message}</span>
            <span className="graph-tooltip-meta">
              {hovered.author}
              {hovered.refs.length > 0 && ` · ${hovered.refs.join(", ")}`}
              {hovered.tags.length > 0 && ` · 🏷 ${hovered.tags.join(", ")}`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
