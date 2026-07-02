import { useState } from "react";
import { Link } from "react-router-dom";
import { useProcessingQueue } from "../../context/ProcessingQueueContext.jsx";
import { Badge } from "../common/Badge.jsx";

const LAYERS = ["queued", "parsing", "extracting", "normalizing", "validating", "correcting", "saving"];

export function ProcessingQueue() {
  const { queue, inFlightCount, todayCount } = useProcessingQueue();
  const [collapsed, setCollapsed] = useState(true);

  const active = queue.filter((q) => !["complete"].includes(q.status));

  if (!active.length && collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="fixed bottom-4 right-4 z-40 px-3 py-2 rounded-full bg-slate-800 border border-slate-700 text-xs text-slate-300"
      >
        Processing {inFlightCount > 0 ? `(${inFlightCount})` : ""}
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 w-80 max-h-96 overflow-auto rounded-lg border border-slate-700 bg-slate-900 shadow-xl">
      <div className="flex items-center justify-between p-3 border-b border-slate-800">
        <span className="text-sm font-medium">
          Processing ({inFlightCount}) · Today: {todayCount}
        </span>
        <button type="button" onClick={() => setCollapsed(!collapsed)} className="text-slate-400 text-xs">
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </div>
      {!collapsed && (
        <ul className="p-2 space-y-2">
          {active.slice(0, 10).map((item) => {
            const layer = item.progress?.current_layer || 0;
            return (
              <li key={item.document_id} className="p-2 rounded bg-slate-800/50 text-xs">
                <div className="flex justify-between gap-2">
                  <span className="truncate">{item.filename}</span>
                  <Badge status={item.status}>{item.status}</Badge>
                </div>
                <div className="mt-1 flex gap-0.5">
                  {LAYERS.map((_, i) => (
                    <span
                      key={i}
                      className={`h-1 flex-1 rounded ${i < layer ? "bg-blue-500" : "bg-slate-700"}`}
                    />
                  ))}
                </div>
                {item.error_details && (
                  <p className="mt-1 text-red-400">{item.error_details}</p>
                )}
                {item.status === "needs_review" && (
                  <Link to="/review" className="text-amber-400 underline mt-1 inline-block">
                    Review
                  </Link>
                )}
                {item.status === "complete" && (
                  <Link to={`/documents/${item.document_id}`} className="text-blue-400 underline mt-1 inline-block">
                    View
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
