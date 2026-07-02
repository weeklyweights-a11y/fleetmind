import { Link } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { formatCurrency } from "../utils/format.js";

export default function VendorList() {
  const { data, loading, error, refetch } = useSubAgent(() => apiGet("/api/vendors"));

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const vendors = data.vendors || [];
  const conc = data.concentration || {};

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold mb-2">Vendors</h1>
      {conc.top_vendor_pct > 50 && (
        <p className="text-amber-400 text-sm mb-4">
          Concentration warning: top vendor is {conc.top_vendor_pct}% of fleet spend
        </p>
      )}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="text-left p-3">Name</th>
              <th className="text-right p-3">Spend</th>
              <th className="text-right p-3">Events</th>
              <th className="text-right p-3">Trucks</th>
              <th className="text-left p-3">Top Category</th>
            </tr>
          </thead>
          <tbody>
            {vendors.map((v) => (
              <tr key={v.id} className="border-t border-slate-800 hover:bg-slate-900/50">
                <td className="p-3">
                  <Link to={`/vendors/${v.id}`} className="text-blue-400">{v.name}</Link>
                </td>
                <td className="p-3 text-right">{formatCurrency(v.total_spend)}</td>
                <td className="p-3 text-right">{v.event_count}</td>
                <td className="p-3 text-right">{v.truck_count}</td>
                <td className="p-3">{v.top_category || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
