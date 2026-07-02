import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { GraphView } from "../components/graph/GraphView.jsx";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { Badge } from "../components/common/Badge.jsx";
import { TruckUploadZone } from "../components/upload/TruckUploadZone.jsx";
import { formatCurrency, formatDate } from "../utils/format.js";

const COLORS = ["#3b82f6", "#22c55e", "#f97316", "#a855f7", "#ef4444"];

export default function TruckDetail() {
  const { id } = useParams();
  const [patternDetail, setPatternDetail] = useState(null);

  const identity = useSubAgent(() => apiGet(`/api/trucks/${id}`), { topic: `truck_${id}_identity` });
  const assignment = useSubAgent(() => apiGet(`/api/trucks/${id}/assignment`), { topic: `truck_${id}_assignment` });
  const maintenance = useSubAgent(
    () => apiGet(`/api/trucks/${id}/maintenance`, { include_trend: true }),
    { topic: `truck_${id}_maintenance` }
  );
  const compliance = useSubAgent(() => apiGet(`/api/trucks/${id}/compliance`), { topic: `truck_${id}_compliance` });
  const financials = useSubAgent(() => apiGet(`/api/trucks/${id}/financials`), { topic: `truck_${id}_financials` });
  const documents = useSubAgent(() => apiGet(`/api/trucks/${id}/documents`), { topic: `truck_${id}_documents` });
  const graph = useSubAgent(() => apiGet(`/api/trucks/${id}/graph`), { topic: `truck_${id}_identity` });

  const unit = identity.data?.unit_number || id;

  const copyVin = useCallback(() => {
    if (identity.data?.vin) navigator.clipboard.writeText(identity.data.vin);
  }, [identity.data?.vin]);

  return (
    <div className="p-4 md:p-6">
      <div className="mb-4">
        <Link to="/trucks" className="text-sm text-slate-400 hover:text-white">← Trucks</Link>
        <h1 className="text-2xl font-bold mt-1">Unit {unit}</h1>
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 space-y-4">
          <Panel title="Identity" loading={identity.loading} error={identity.error} onRetry={identity.refetch}>
            {identity.data && (
              <div>
                <p className="text-3xl font-bold">#{identity.data.unit_number}</p>
                <p className="text-slate-400">{identity.data.year} {identity.data.make} {identity.data.model}</p>
                <button type="button" onClick={copyVin} className="font-mono text-sm text-slate-300 mt-2 hover:text-white">
                  {identity.data.vin} (copy)
                </button>
                <div className="mt-2 flex items-center gap-2">
                  {identity.data.color && (
                    <span className="w-4 h-4 rounded-full border border-slate-600" style={{ background: identity.data.color }} />
                  )}
                  <Badge status={identity.data.status}>{identity.data.status}</Badge>
                </div>
                {identity.data.purchase_price && (
                  <p className="text-sm mt-2">
                    Acquired {formatDate(identity.data.acquired_date)} for {formatCurrency(identity.data.purchase_price)}
                  </p>
                )}
              </div>
            )}
          </Panel>

          <Panel title="Maintenance" loading={maintenance.loading} error={maintenance.error} onRetry={maintenance.refetch}>
            {maintenance.data && (
              <div className="space-y-4">
                <div className="flex gap-6">
                  <div>
                    <p className="text-2xl font-bold">{formatCurrency(maintenance.data.summary?.total_spend)}</p>
                    <p className="text-xs text-slate-500">{maintenance.data.summary?.event_count} events</p>
                  </div>
                  {maintenance.data.fleet_comparison && (
                    <p className="text-sm text-slate-400 self-end">
                      {maintenance.data.fleet_comparison.difference_pct > 0 ? "↑" : "↓"}{" "}
                      {Math.abs(maintenance.data.fleet_comparison.difference_pct)}% vs fleet avg
                    </p>
                  )}
                </div>
                {(maintenance.data.trend || []).length > 0 && (
                  <ResponsiveContainer width="100%" height={160}>
                    <LineChart data={maintenance.data.trend}>
                      <XAxis dataKey="month" tick={{ fontSize: 10 }} stroke="#64748b" />
                      <YAxis tick={{ fontSize: 10 }} stroke="#64748b" />
                      <Tooltip />
                      <Line type="monotone" dataKey="spend" stroke="#3b82f6" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <ResponsiveContainer width="100%" height={120}>
                    <PieChart>
                      <Pie data={maintenance.data.by_category || []} dataKey="total_spend" nameKey="category" cx="50%" cy="50%" outerRadius={40}>
                        {(maintenance.data.by_category || []).map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart data={(maintenance.data.by_vendor || []).slice(0, 5)} layout="vertical">
                      <XAxis type="number" hide />
                      <YAxis type="category" dataKey="vendor_name" width={80} tick={{ fontSize: 9 }} />
                      <Bar dataKey="total_spend" fill="#3b82f6" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                {(maintenance.data.patterns || []).map((p, i) => (
                  <div
                    key={i}
                    className={`p-2 rounded text-sm ${p.severity === "high" ? "bg-red-900/30 border border-red-800" : "bg-amber-900/30 border border-amber-800"}`}
                  >
                    {p.description}
                    <button type="button" className="ml-2 text-blue-400 underline" onClick={() => setPatternDetail(p)}>
                      details
                    </button>
                  </div>
                ))}
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {(maintenance.data.events || []).map((e) => (
                    <Link
                      key={e.event_id}
                      to={`/documents/${e.source_document_id}`}
                      className="flex justify-between text-sm p-2 rounded hover:bg-slate-800"
                    >
                      <span>{formatDate(e.service_date)} · {e.vendor_name} · {e.category}</span>
                      <span>{formatCurrency(e.cost)} <Badge status={e.payment_status}>{e.payment_status}</Badge></span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </Panel>

          <Panel title="Financials" loading={financials.loading} error={financials.error} onRetry={financials.refetch}>
            {financials.data && (
              <div>
                <p className="text-2xl font-bold">{formatCurrency(financials.data.total_cost_of_ownership)}</p>
                <p className="text-sm text-slate-400">Total cost of ownership</p>
                {financials.data.cost_per_mile != null && (
                  <p className="mt-2">{formatCurrency(financials.data.cost_per_mile)}/mile</p>
                )}
              </div>
            )}
          </Panel>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <Panel title="Compliance" loading={compliance.loading} error={compliance.error} onRetry={compliance.refetch}>
            {compliance.data && (
              <ul className="space-y-2 text-sm">
                {Object.entries(compliance.data.categories || {}).map(([key, cat]) => (
                  <li key={key} className="flex justify-between p-2 rounded bg-slate-800/50">
                    <span className="capitalize">{key.replace("_", " ")}</span>
                    <span>{cat.status} · {cat.days_remaining ?? "—"}d</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Assignment" loading={assignment.loading} error={assignment.error} onRetry={assignment.refetch}>
            {assignment.data?.current_driver ? (
              <div>
                <Link to={`/drivers/${assignment.data.current_driver.driver_code}`} className="text-blue-400 font-medium">
                  {assignment.data.current_driver.full_name}
                </Link>
                <p className="text-sm text-slate-400">CDL {assignment.data.current_driver.license_class} · expires {formatDate(assignment.data.current_driver.license_expiry_date)}</p>
              </div>
            ) : (
              <p className="text-sm text-slate-500">{assignment.data?.unassigned_reason || "No current assignment"}</p>
            )}
          </Panel>

          <Panel title="Documents" loading={documents.loading} error={documents.error} onRetry={documents.refetch}>
            {(documents.data?.groups || []).map((g) => (
              <div key={g.document_type} className="mb-3">
                <p className="text-xs text-slate-500 uppercase">{g.document_type} ({g.count})</p>
                {(g.documents || []).map((d) => (
                  <Link key={d.document_id} to={`/documents/${d.document_id}`} className="block text-sm text-blue-400 py-0.5">
                    {d.document_number || d.document_id}
                  </Link>
                ))}
              </div>
            ))}
            <TruckUploadZone truckUnit={unit} />
          </Panel>

          <Panel title="Relationship Graph">
            <GraphView data={graph.data} height={250} />
          </Panel>
        </div>
      </div>

      {patternDetail && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setPatternDetail(null)}>
          <div className="bg-slate-900 rounded-lg p-4 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold mb-2">Pattern Details</h3>
            <pre className="text-xs overflow-auto">{JSON.stringify(patternDetail.supporting_data || patternDetail, null, 2)}</pre>
            <button type="button" onClick={() => setPatternDetail(null)} className="mt-2 text-sm text-slate-400">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Panel({ title, loading, error, onRetry, children }) {
  return (
    <section className="rounded-lg border border-slate-800 p-4">
      <h2 className="text-sm font-semibold mb-3">{title}</h2>
      {loading && <Skeleton className="h-20" />}
      {error && <ErrorPanel message={error} onRetry={onRetry} />}
      {!loading && !error && children}
    </section>
  );
}
