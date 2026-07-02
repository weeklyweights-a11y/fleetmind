import { useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { Badge } from "../components/common/Badge.jsx";
import { formatDate } from "../utils/format.js";

export default function DocumentList() {
  const [docType, setDocType] = useState("");
  const [status, setStatus] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");

  const { data, loading, error, refetch } = useSubAgent(
    () => apiGet("/api/documents", {
      document_type: docType || undefined,
      processing_status: status || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      limit: 50,
    }),
    { deps: [docType, status, sortBy, sortOrder] }
  );

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const items = data.items || [];

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold mb-4">Documents</h1>
      <div className="flex flex-wrap gap-2 mb-4">
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="bg-slate-800 rounded px-3 py-1.5 text-sm">
          <option value="created_at">Created</option>
          <option value="document_date">Document Date</option>
          <option value="original_filename">Filename</option>
          <option value="processing_status">Status</option>
        </select>
        <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} className="bg-slate-800 rounded px-3 py-1.5 text-sm">
          <option value="desc">Desc</option>
          <option value="asc">Asc</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="bg-slate-800 rounded px-3 py-1.5 text-sm">
          <option value="">All statuses</option>
          <option value="complete">Complete</option>
          <option value="needs_review">Needs Review</option>
          <option value="failed">Failed</option>
        </select>
        <input
          type="text"
          placeholder="Document type filter"
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
          className="bg-slate-800 rounded px-3 py-1.5 text-sm"
        />
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="text-left p-3">Filename</th>
              <th className="text-left p-3">Type</th>
              <th className="text-left p-3">Truck</th>
              <th className="text-left p-3">Date</th>
              <th className="text-left p-3">Status</th>
              <th className="text-right p-3">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} className="border-t border-slate-800 hover:bg-slate-900/50">
                <td className="p-3">
                  <Link to={`/documents/${d.id}`} className="text-blue-400">{d.original_filename}</Link>
                </td>
                <td className="p-3">{d.document_type || "—"}</td>
                <td className="p-3">{d.truck_unit ?? "—"}</td>
                <td className="p-3">{formatDate(d.document_date || d.created_at)}</td>
                <td className="p-3"><Badge status={d.processing_status}>{d.processing_status}</Badge></td>
                <td className="p-3 text-right">
                  {d.entity_resolution_confidence != null
                    ? `${(Number(d.entity_resolution_confidence) * 100).toFixed(0)}%`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
