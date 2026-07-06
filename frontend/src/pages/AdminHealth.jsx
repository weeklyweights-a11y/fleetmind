import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";

function Panel({ title, children }) {
  return (
    <section className="rounded-lg border border-slate-800 p-4">
      <h2 className="text-sm font-semibold mb-3">{title}</h2>
      {children}
    </section>
  );
}

export default function AdminHealth() {
  const { data, loading, error, refetch } = useSubAgent(() => apiGet("/api/admin/health"));

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  return (
    <div className="p-4 md:p-6 space-y-4">
      <h1 className="text-xl font-bold">System Health (Admin)</h1>
      <div className="grid lg:grid-cols-2 gap-4">
        <Panel title="Extraction">
          <p className="text-sm">Overall accuracy: {data.extraction?.overall_accuracy_pct}%</p>
          <p className="text-sm text-slate-400">Processed: {data.extraction?.total_processed}</p>
          <pre className="text-xs mt-2 overflow-auto">{JSON.stringify(data.extraction?.by_document_type, null, 2)}</pre>
        </Panel>
        <Panel title="Entity Resolution">
          <p className="text-sm">Auto rate: {data.entity_resolution?.auto_resolution_rate_pct}%</p>
          <p className="text-sm">Human review: {data.entity_resolution?.human_review_rate_pct}%</p>
          <ul className="text-xs mt-2 space-y-1">
            {(data.entity_resolution?.common_failures || []).map((f) => (
              <li key={f.document_id}>{f.document_type} — conf {f.confidence ?? "n/a"}</li>
            ))}
          </ul>
        </Panel>
        <Panel title="Conversation Quality">
          <p className="text-sm">Conversations: {data.conversation_quality?.total_conversations}</p>
          <p className="text-sm">Avg turns: {data.conversation_quality?.avg_turns_per_conversation}</p>
          <p className="text-sm">Satisfaction: {data.conversation_quality?.query_satisfaction_rate_pct}%</p>
        </Panel>
        <Panel title="Fleet Intelligence">
          <p className="text-sm">Total anomalies: {data.fleet_intelligence?.total_anomalies}</p>
          <p className="text-sm">Precision: {data.fleet_intelligence?.precision_pct}%</p>
          <p className="text-sm">Dismiss rate: {data.fleet_intelligence?.dismiss_rate_pct}%</p>
        </Panel>
        <Panel title="Document Type Evolution">
          <p className="text-sm">Unknown rate: {data.document_type_evolution?.unknown_document_rate_pct}%</p>
        </Panel>
        <Panel title="System Activity">
          <p className="text-sm">Queue depth: {data.system_activity?.queue_depth}</p>
          <ul className="text-xs mt-2 space-y-1 max-h-48 overflow-auto">
            {(data.system_activity?.background_job_runs || []).map((j, i) => (
              <li key={i}>{j.process_name} — {j.entities_processed} entities, {j.anomalies_created} anomalies</li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
