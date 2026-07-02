import { useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { Badge } from "../components/common/Badge.jsx";
import { formatDate } from "../utils/format.js";

export default function ReviewQueue() {
  const { data, loading, error, refetch } = useSubAgent(() => apiGet("/api/documents/review"));
  const [selected, setSelected] = useState(null);
  const [extraction, setExtraction] = useState(null);
  const [edits, setEdits] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const selectDoc = async (doc) => {
    setSelected(doc);
    setEdits({});
    setSubmitError(null);
    try {
      const ext = await apiGet(`/api/documents/${doc.id}/extraction`);
      setExtraction(ext);
    } catch {
      setExtraction(null);
    }
  };

  const submitReview = async (action) => {
    if (!selected) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const corrections = Object.entries(edits).map(([field_name, corrected_value]) => ({
        field_name,
        corrected_value,
        target_table: "maintenance_events",
        target_column: field_name,
      }));
      await apiPost(`/api/documents/${selected.id}/review`, {
        action,
        corrections: action === "correct" ? corrections : [],
        corrected_by: "reviewer",
        reprocess: false,
        reject_reason: action === "reject" ? "Rejected by reviewer" : undefined,
      });
      setSelected(null);
      setExtraction(null);
      refetch();
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const items = data.items || [];

  return (
    <div className="p-4 md:p-6 grid lg:grid-cols-2 gap-4">
      <div>
        <h1 className="text-xl font-bold mb-4">Review Queue ({items.length})</h1>
        {items.length === 0 ? (
          <p className="text-slate-500">No documents pending review.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((doc) => (
              <li key={doc.id}>
                <button
                  type="button"
                  onClick={() => selectDoc(doc)}
                  className={`w-full text-left p-3 rounded border ${
                    selected?.id === doc.id ? "border-blue-500 bg-slate-800" : "border-slate-800 hover:bg-slate-900"
                  }`}
                >
                  <p className="font-medium">{doc.original_filename}</p>
                  <p className="text-xs text-slate-400">{doc.document_type} · {formatDate(doc.created_at)}</p>
                  <Badge status={doc.processing_status}>{doc.processing_status}</Badge>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-slate-800 p-4">
        {!selected ? (
          <p className="text-slate-500 text-sm">Select a document to review</p>
        ) : (
          <>
            <h2 className="font-semibold mb-2">{selected.original_filename}</h2>
            <Link to={`/documents/${selected.id}`} className="text-sm text-blue-400">Open in viewer</Link>
            <ul className="mt-4 space-y-2 text-sm max-h-64 overflow-y-auto">
              {(extraction?.fields || []).map((f) => (
                <li key={f.name} className={f.validation_error ? "bg-red-900/20 p-2 rounded" : ""}>
                  <label className="text-slate-400 text-xs">{f.name}</label>
                  <input
                    type="text"
                    defaultValue={f.value ?? ""}
                    onChange={(e) => setEdits((prev) => ({ ...prev, [f.name]: e.target.value }))}
                    className="w-full bg-slate-800 rounded px-2 py-1 mt-1"
                  />
                  {f.validation_error && <p className="text-xs text-red-400">{f.validation_error}</p>}
                </li>
              ))}
            </ul>
            {submitError && <p className="text-red-400 text-sm mt-2">{submitError}</p>}
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                disabled={submitting}
                onClick={() => submitReview("approve")}
                className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded text-sm"
              >
                Approve
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => submitReview("correct")}
                className="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 rounded text-sm"
              >
                Submit Corrections
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => submitReview("reject")}
                className="px-3 py-1.5 bg-red-800 hover:bg-red-700 rounded text-sm"
              >
                Reject
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
