import { Link } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { complianceColor, formatDate } from "../utils/format.js";

export default function DriverList() {
  const { data, loading, error, refetch } = useSubAgent(() => apiGet("/api/drivers", { per_page: 50 }));

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const items = data.items || [];

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-bold mb-4">Drivers</h1>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="text-left p-3">Code</th>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">CDL Class</th>
              <th className="text-left p-3">Endorsements</th>
              <th className="text-left p-3">Expiry</th>
              <th className="text-left p-3">Truck</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} className="border-t border-slate-800 hover:bg-slate-900/50">
                <td className="p-3">
                  <Link to={`/drivers/${d.driver_code || d.id}`} className="text-blue-400">{d.driver_code}</Link>
                </td>
                <td className="p-3">{d.full_name}</td>
                <td className="p-3">{d.license_class}</td>
                <td className="p-3">{d.endorsements || "—"}</td>
                <td className="p-3">
                  <span className={`inline-block w-2 h-2 rounded-full mr-1 ${complianceColor(d.expiry_status)}`} />
                  {formatDate(d.license_expiry_date)}
                </td>
                <td className="p-3">
                  {d.current_truck_unit ? (
                    <Link to={`/trucks/${d.current_truck_unit}`} className="text-blue-400">{d.current_truck_unit}</Link>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
