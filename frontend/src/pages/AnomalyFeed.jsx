import { useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPatch } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { useChat } from "../context/ChatContext.jsx";
import { EmptyState } from "../components/common/EmptyState.jsx";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { Badge } from "../components/common/Badge.jsx";

const SEVERITIES = ["all", "critical", "warning", "info"];
const STATUSES = ["all", "new", "acknowledged", "investigating"];

export default function AnomalyFeed() {
  const [severity, setSeverity] = useState("all");
  const [status, setStatus] = useState("all");
  const [dismissId, setDismissId] = useState(null);
  const [dismissReason, setDismissReason] = useState("");
  const { prefillChat } = useChat();

  const query = () => {
    const params = new URLSearchParams();
    if (severity !== "all") params.set("severity", severity);
    if (status !== "all") params.set("status", status);
    const qs = params.toString();
    return apiGet(`/api/anomalies${qs ? `?${qs}` : ""}`);
  };

  const { data, loading, refetch } = useSubAgent(query, { topic: "anomalies" });
  const items = data?.anomalies || [];

  const patchStatus = async (anomalyId, newStatus, reason) => {
    await apiPatch(`/api/anomalies/${anomalyId}`, {
      status: newStatus,
      reason,
      operator_name: "default",
    });
    setDismissId(null);
    setDismissReason("");
    refetch();
  };

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold mb-4">Anomalies</h1>
      <div className="flex gap-2 mb-4 flex-wrap">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-slate-800 rounded px-3 py-1.5 text-sm"
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s === "all" ? "All severities" : s}</option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="bg-slate-800 rounded px-3 py-1.5 text-sm"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s === "all" ? "All statuses" : s}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <Skeleton className="h-48" />
      ) : items.length === 0 ? (
        <EmptyState title="No anomalies detected" message="The system will surface anomalies as data is analyzed." />
      ) : (
        <ul className="space-y-3">
          {items.map((a) => (
            <li key={a.anomaly_id} className="p-4 rounded border border-slate-800">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <Badge status={a.severity}>{a.severity}</Badge>
                  <span className="ml-2 text-xs text-slate-500">{a.status}</span>
                  {a.follow_up && <span className="ml-2 text-xs text-amber-400">follow-up</span>}
                  <p className="mt-2 text-sm">{a.description}</p>
                  {a.entity_name && (
                    <p className="text-xs text-slate-400 mt-1">
                      {a.entity_type}: {a.entity_name}
                    </p>
                  )}
                  <p className="text-xs text-slate-500 mt-1">{new Date(a.detected_at).toLocaleString()}</p>
                </div>
              </div>
              <div className="flex gap-2 mt-3 flex-wrap">
                <button type="button" className="px-2 py-1 text-xs rounded bg-slate-800" onClick={() => patchStatus(a.anomaly_id, "acknowledged")}>
                  Acknowledge
                </button>
                <button type="button" className="px-2 py-1 text-xs rounded bg-slate-800" onClick={() => patchStatus(a.anomaly_id, "investigating")}>
                  Investigate
                </button>
                <button type="button" className="px-2 py-1 text-xs rounded bg-slate-800" onClick={() => setDismissId(a.anomaly_id)}>
                  Dismiss
                </button>
                <button type="button" className="px-2 py-1 text-xs rounded bg-slate-800" onClick={() => prefillChat(`Tell me more about: ${a.description}`)}>
                  Ask in chat
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {dismissId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-4 max-w-md w-full">
            <h3 className="font-semibold mb-2">Dismiss anomaly</h3>
            <textarea
              className="w-full bg-slate-800 rounded p-2 text-sm"
              rows={3}
              placeholder="Reason (required)"
              value={dismissReason}
              onChange={(e) => setDismissReason(e.target.value)}
            />
            <div className="flex gap-2 mt-3 justify-end">
              <button type="button" className="px-3 py-1 rounded bg-slate-800" onClick={() => setDismissId(null)}>Cancel</button>
              <button
                type="button"
                className="px-3 py-1 rounded bg-red-900"
                disabled={!dismissReason.trim()}
                onClick={() => patchStatus(dismissId, "dismissed", dismissReason.trim())}
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-2 mt-6">
        {["What's flagged right now?", "Anything I was tracking?"].map((label) => (
          <button key={label} type="button" className="px-3 py-1.5 rounded bg-slate-800 text-sm" onClick={() => prefillChat(label)}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
