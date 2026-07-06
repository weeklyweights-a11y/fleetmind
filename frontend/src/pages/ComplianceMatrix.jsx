import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useChat } from "../context/ChatContext.jsx";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { complianceColor } from "../utils/format.js";

const CATEGORIES = ["insurance", "registration", "title", "emission", "driver_cdl", "medical_cert"];

export default function ComplianceMatrix() {
  const [params] = useSearchParams();
  const statusFilter = params.get("status");
  const [tick, setTick] = useState(0);
  const { prefillChat, setOpen } = useChat();

  const { data, loading, error, refetch } = useSubAgent(() => apiGet("/api/compliance/matrix"), {
    topic: "compliance_matrix",
  });

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 3600000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const matrix = (data.matrix || []).filter((row) => {
    if (!statusFilter) return true;
    return CATEGORIES.some((c) => row[c]?.status === statusFilter);
  });

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Compliance Matrix</h1>
        <p className="text-sm text-slate-400">Score: {data.fleet_compliance_score?.toFixed(1)}%</p>
      </div>

      {statusFilter && (
        <p className="text-sm text-slate-400">
          Filtered by status: {statusFilter}. <Link to="/compliance" className="text-blue-400">Clear</Link>
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-xs">
          <thead className="bg-slate-900">
            <tr>
              <th className="p-2 text-left">Unit</th>
              {CATEGORIES.map((c) => (
                <th key={c} className="p-2 capitalize">{c.replace("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row) => (
              <tr key={row.truck_unit} className="border-t border-slate-800">
                <td className="p-2">
                  <Link to={`/trucks/${row.truck_unit}`} className="text-blue-400">{row.truck_unit}</Link>
                </td>
                {CATEGORIES.map((c) => {
                  const cell = row[c] || {};
                  return (
                    <td
                      key={c}
                      className="p-2 text-center cursor-pointer"
                      title={`${cell.days ?? ""} days — click for details`}
                      onClick={() => {
                        setOpen(true);
                        prefillChat(`Tell me about truck ${row.truck_unit}'s ${c.replace("_", " ")}`);
                      }}
                    >
                      <span className={`inline-block w-3 h-3 rounded-full ${complianceColor(cell.status)}`} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section>
        <h2 className="text-sm font-semibold mb-3">Upcoming Deadlines</h2>
        <ul className="space-y-2 text-sm">
          {(data.deadlines || []).map((d, i) => {
            const days = d.days_remaining - (tick > 0 ? 0 : 0);
            return (
              <li key={i} className="flex justify-between p-2 rounded bg-slate-800/50">
                <Link to={`/trucks/${d.truck_unit}`} className="text-blue-400">Unit {d.truck_unit}</Link>
                <span>{d.compliance_type} · {d.expiry_date} · {days}d</span>
                <span className={`w-2 h-2 rounded-full ${complianceColor(d.severity)}`} />
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
