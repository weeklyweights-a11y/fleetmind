import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet, fileUrl } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { Badge } from "../components/common/Badge.jsx";

export default function DocumentViewer() {
  const { id } = useParams();
  const doc = useSubAgent(() => apiGet(`/api/documents/${id}`));
  const extraction = useSubAgent(() => apiGet(`/api/documents/${id}/extraction`));
  const [list, setList] = useState([]);

  useEffect(() => {
    apiGet("/api/documents", { limit: 100, sort_by: "created_at", sort_order: "desc" })
      .then((d) => setList(d.items || []))
      .catch(() => {});
  }, []);

  const idx = list.findIndex((d) => d.id === id);
  const prev = idx > 0 ? list[idx - 1] : null;
  const next = idx >= 0 && idx < list.length - 1 ? list[idx + 1] : null;

  if (doc.loading) return <div className="p-6"><Skeleton className="h-96" /></div>;
  if (doc.error) return <div className="p-6"><ErrorPanel message={doc.error} onRetry={doc.refetch} /></div>;

  return (
    <div className="p-4 md:p-6 h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <Link to="/documents" className="text-sm text-slate-400 hover:text-white">← Documents</Link>
          <h1 className="text-lg font-bold">{doc.data?.original_filename}</h1>
          <Badge status={doc.data?.processing_status}>{doc.data?.processing_status}</Badge>
        </div>
        <div className="flex gap-2 text-sm">
          {prev && <Link to={`/documents/${prev.id}`} className="text-blue-400">← Prev</Link>}
          {next && <Link to={`/documents/${next.id}`} className="text-blue-400">Next →</Link>}
        </div>
      </div>
      <div className="flex-1 grid lg:grid-cols-2 gap-4 min-h-0">
        <div className="rounded-lg border border-slate-800 overflow-hidden bg-slate-900">
          <iframe title="PDF" src={fileUrl(id)} className="w-full h-full min-h-[400px]" />
        </div>
        <div className="rounded-lg border border-slate-800 p-4 overflow-y-auto">
          <h2 className="text-sm font-semibold mb-3">Extracted Fields</h2>
          {extraction.loading ? (
            <Skeleton className="h-32" />
          ) : extraction.error ? (
            <ErrorPanel message={extraction.error} onRetry={extraction.refetch} />
          ) : (
            <ul className="space-y-2 text-sm">
              {(extraction.data?.fields || []).map((f) => (
                <li
                  key={f.name}
                  className={`p-2 rounded ${f.validation_error ? "bg-red-900/20 border border-red-800" : f.corrected ? "bg-amber-900/20" : "bg-slate-800/50"}`}
                >
                  <div className="flex justify-between">
                    <span className="text-slate-400">{f.name}</span>
                    {f.confidence != null && (
                      <span className="text-xs text-slate-500">{(f.confidence * 100).toFixed(0)}%</span>
                    )}
                  </div>
                  <p className="font-medium">{String(f.value ?? "—")}</p>
                  {f.corrected && (
                    <p className="text-xs text-amber-400">Corrected ({f.correction_source})</p>
                  )}
                  {f.validation_error && (
                    <p className="text-xs text-red-400">{f.validation_error}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
