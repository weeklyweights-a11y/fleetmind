import { useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import ForceGraph2D from "react-force-graph-2d";

const NODE_COLORS = {
  Truck: "#3b82f6",
  Driver: "#22c55e",
  Vendor: "#f97316",
  InsurancePolicy: "#a855f7",
  Document: "#64748b",
  default: "#94a3b8",
};

function normalizeGraph(data) {
  if (!data) return { nodes: [], links: [] };
  const nodes = (data.nodes || []).map((n) => ({
    id: n.id,
    label: n.label || n.properties?.name || n.type || n.id,
    type: n.type || "default",
  }));
  const links = (data.edges || data.links || []).map((e) => ({
    source: e.source,
    target: e.target,
    type: e.type,
  }));
  return { nodes, links };
}

export function GraphView({ data, height = 400 }) {
  const ref = useRef();
  const navigate = useNavigate();
  const graph = useMemo(() => normalizeGraph(data), [data]);

  const paintNode = useCallback((node, ctx, globalScale) => {
    const color = NODE_COLORS[node.type] || NODE_COLORS.default;
    const r = node.type === "Document" ? 4 : 8;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    if (globalScale > 0.8) {
      ctx.font = `${10 / globalScale}px sans-serif`;
      ctx.fillStyle = "#e2e8f0";
      ctx.fillText(node.label?.slice(0, 20) || node.type, node.x + r + 2, node.y + 3);
    }
  }, []);

  const onNodeClick = useCallback(
    (node) => {
      const t = (node.type || "").toLowerCase();
      if (t === "truck") navigate(`/trucks/${node.label}`);
      else if (t === "driver") navigate(`/drivers/${node.id}`);
      else if (t === "vendor") navigate(`/vendors/${node.id}`);
    },
    [navigate]
  );

  useEffect(() => {
    if (ref.current) ref.current.d3Force("charge")?.strength(-120);
  }, [graph]);

  if (!graph.nodes.length) {
    return <p className="text-sm text-slate-500 py-8 text-center">No graph data</p>;
  }

  return (
    <div className="relative">
      <div className="absolute top-2 right-2 z-10 flex flex-wrap gap-2 text-xs">
        {Object.entries(NODE_COLORS)
          .filter(([k]) => k !== "default")
          .map(([type, color]) => (
            <span key={type} className="flex items-center gap-1 text-slate-400">
              <span className="w-2 h-2 rounded-full" style={{ background: color }} />
              {type}
            </span>
          ))}
      </div>
      <ForceGraph2D
        ref={ref}
        graphData={graph}
        height={height}
        backgroundColor="#020617"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          const r = 10;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.fill();
        }}
        linkColor={() => "#475569"}
        linkDirectionalArrowLength={4}
        onNodeClick={onNodeClick}
      />
    </div>
  );
}
