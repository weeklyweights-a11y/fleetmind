import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { GraphView } from "../components/graph/GraphView.jsx";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { formatCurrency, formatPercent, timeAgo, complianceColor } from "../utils/format.js";

export default function FleetOverview() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");
  const { data, loading, error, refetch } = useSubAgent(() => apiGet("/api/fleet/overview"), {
    topic: "fleet_stats",
  });
  const graph = useSubAgent(() => apiGet("/api/fleet/graph"), { topic: "fleet_stats" });

  if (loading) return <div className="p-6 space-y-4"><Skeleton className="h-24" /><Skeleton className="h-48" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const comp = data.fleet_composition || {};
  const snap = data.compliance_snapshot || {};
  const fin = data.financial_snapshot || {};
  const total = (snap.fully_compliant || 0) + (snap.warnings || 0) + (snap.expirations || 0) + (snap.incomplete || 0);

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex gap-2">
        <button type="button" onClick={() => setTab("overview")} className={`px-3 py-1 rounded text-sm ${tab === "overview" ? "bg-slate-800" : ""}`}>Overview</button>
        <button type="button" onClick={() => setTab("graph")} className={`px-3 py-1 rounded text-sm ${tab === "graph" ? "bg-slate-800" : ""}`}>Fleet Graph</button>
      </div>

      {tab === "graph" ? (
        <GraphView data={graph.data} height={500} />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard title="Total Trucks" value={comp.active} sub={`${comp.sold} sold · ${comp.inactive} inactive`} />
            <StatCard title="Total Drivers" value={comp.assigned_drivers} sub={`${comp.unassigned_drivers} unassigned`} />
            <StatCard title="Fleet Value" value={formatCurrency(comp.total_fleet_value)} />
            <StatCard
              title="This Month"
              value={formatCurrency(fin.this_month_spend)}
              sub={fin.mom_change_pct != null ? formatPercent(fin.mom_change_pct) : ""}
              subColor={fin.mom_change_pct > 0 ? "text-red-400" : "text-emerald-400"}
            />
          </div>

          <section className="rounded-lg border border-slate-800 p-4">
            <h2 className="text-sm font-semibold mb-3">Compliance Health</h2>
            <div className="flex h-4 rounded overflow-hidden">
              {[
                { key: "fully_compliant", color: "bg-emerald-500", status: "green" },
                { key: "warnings", color: "bg-amber-500", status: "yellow" },
                { key: "expirations", color: "bg-red-500", status: "red" },
                { key: "incomplete", color: "bg-slate-500", status: "grey" },
              ].map(({ key, color, status }) => (
                <button
                  key={key}
                  type="button"
                  style={{ width: total ? `${((snap[key] || 0) / total) * 100}%` : "25%" }}
                  className={`${color} min-w-[2px] hover:opacity-80`}
                  onClick={() => navigate(`/compliance?status=${status}`)}
                  title={`${snap[key] || 0} trucks`}
                />
              ))}
            </div>
            <div className="flex gap-4 mt-2 text-xs text-slate-400">
              <span>{snap.fully_compliant} compliant</span>
              <span>{snap.warnings} warnings</span>
              <span>{snap.expirations} expired</span>
              <span>{snap.incomplete} incomplete</span>
            </div>
          </section>

          <div className="grid lg:grid-cols-2 gap-4">
            <section className="rounded-lg border border-slate-800 p-4">
              <h2 className="text-sm font-semibold mb-3">Upcoming Deadlines</h2>
              {(snap.urgent_items || []).length === 0 ? (
                <p className="text-sm text-slate-500">All clear — no upcoming deadlines.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {(snap.urgent_items || []).slice(0, 5).map((item, i) => (
                    <li key={i} className="flex justify-between">
                      <Link to={`/trucks/${item.truck_unit}`} className="text-blue-400">
                        Unit {item.truck_unit}
                      </Link>
                      <span>{item.compliance_type} · {item.days_remaining}d</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-lg border border-slate-800 p-4">
              <h2 className="text-sm font-semibold mb-3">Recent Activity</h2>
              <ul className="space-y-2 text-sm">
                {(data.recent_activity || []).map((item) => (
                  <li key={item.document_id} className="flex justify-between gap-2">
                    <span className="truncate">
                      {item.description || item.type}
                      {item.truck_unit && ` · Unit ${item.truck_unit}`}
                    </span>
                    <span className="text-slate-500 shrink-0">{timeAgo(item.created_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section className="rounded-lg border border-slate-800 p-4">
            <h2 className="text-sm font-semibold mb-2">Anomalies</h2>
            <p className="text-sm text-slate-500">No anomalies detected. <Link to="/anomalies" className="text-blue-400">See all</Link></p>
          </section>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <QuickStat label="Maintenance Events" value={data.quick_stats?.total_maintenance_events} />
            <QuickStat label="Vendors" value={data.quick_stats?.total_vendors} />
            <QuickStat label="Avg Cost/Mile" value={formatCurrency(data.quick_stats?.fleet_avg_cost_per_mile)} />
            <QuickStat
              label="Most Expensive"
              value={data.quick_stats?.most_expensive_truck?.unit ? `Unit ${data.quick_stats.most_expensive_truck.unit}` : "—"}
            />
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ title, value, sub, subColor = "text-slate-400" }) {
  return (
    <div className="rounded-lg border border-slate-800 p-4">
      <p className="text-xs text-slate-500">{title}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {sub && <p className={`text-xs mt-1 ${subColor}`}>{sub}</p>}
    </div>
  );
}

function QuickStat({ label, value }) {
  return (
    <div className="rounded border border-slate-800 p-3">
      <p className="text-slate-500 text-xs">{label}</p>
      <p className="font-medium">{value ?? "—"}</p>
    </div>
  );
}
