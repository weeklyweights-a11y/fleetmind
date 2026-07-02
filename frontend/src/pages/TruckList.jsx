import { useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { formatCurrency, complianceColor } from "../utils/format.js";

export default function TruckList() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("unit_number");

  const { data, loading, error, refetch } = useSubAgent(
    () =>
      apiGet("/api/trucks", {
        status: status || undefined,
        search: search || undefined,
        sort_by: sortBy,
        per_page: 50,
      }),
    { topic: "fleet_stats", deps: [status, search, sortBy] }
  );

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const items = data.items || data.trucks || [];

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold mb-4">Trucks</h1>
      <div className="flex flex-wrap gap-2 mb-4">
        <input
          type="search"
          placeholder="Search unit or VIN…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-slate-800 rounded px-3 py-1.5 text-sm"
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="bg-slate-800 rounded px-3 py-1.5 text-sm">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="sold">Sold</option>
          <option value="inactive">Inactive</option>
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="bg-slate-800 rounded px-3 py-1.5 text-sm">
          <option value="unit_number">Unit #</option>
          <option value="year">Year</option>
          <option value="make">Make</option>
        </select>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="text-left p-3">Unit</th>
              <th className="text-left p-3">Make/Model</th>
              <th className="text-left p-3">Year</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Driver</th>
              <th className="text-left p-3">Compliance</th>
              <th className="text-right p-3">Maintenance</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} className="border-t border-slate-800 hover:bg-slate-900/50">
                <td className="p-3">
                  <Link to={`/trucks/${t.unit_number}`} className="text-blue-400 font-medium">
                    {t.unit_number}
                  </Link>
                </td>
                <td className="p-3">{t.make} {t.model}</td>
                <td className="p-3">{t.year}</td>
                <td className="p-3 capitalize">{t.status}</td>
                <td className="p-3">{t.current_driver_name || "—"}</td>
                <td className="p-3">
                  <span className={`inline-block w-2 h-2 rounded-full ${complianceColor(t.overall_compliance_status)}`} />
                </td>
                <td className="p-3 text-right">{formatCurrency(t.total_maintenance_spend)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
