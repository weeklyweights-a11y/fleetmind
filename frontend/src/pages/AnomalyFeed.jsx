import { useState } from "react";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { EmptyState } from "../components/common/EmptyState.jsx";
import { Skeleton } from "../components/common/Skeleton.jsx";

export default function AnomalyFeed() {
  const [severity, setSeverity] = useState("all");
  const [status, setStatus] = useState("all");
  const { data, loading } = useSubAgent(() => apiGet("/api/anomalies"), { topic: "anomalies" });

  const items = data?.items || data?.anomalies || [];

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold mb-4">Anomalies</h1>
      <div className="flex gap-2 mb-4">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-slate-800 rounded px-3 py-1.5 text-sm"
        >
          <option value="all">All severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="bg-slate-800 rounded px-3 py-1.5 text-sm"
        >
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
        </select>
      </div>

      {loading ? (
        <Skeleton className="h-48" />
      ) : items.length === 0 ? (
        <EmptyState
          title="No anomalies detected"
          message="Anomaly detection arrives in Phase 6. Filters and actions are ready when data is available."
        />
      ) : (
        <ul className="space-y-2">
          {items.map((a) => (
            <li key={a.id} className="p-3 rounded border border-slate-800">{a.description}</li>
          ))}
        </ul>
      )}

      <div className="flex gap-2 mt-6">
        {["Acknowledge", "Investigate", "Dismiss"].map((label) => (
          <button
            key={label}
            type="button"
            disabled
            title="Available in Phase 6"
            className="px-3 py-1.5 rounded bg-slate-800 text-slate-500 cursor-not-allowed text-sm"
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
