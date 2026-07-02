import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { GraphView } from "../components/graph/GraphView.jsx";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { complianceColor, formatDate } from "../utils/format.js";

export default function DriverDetail() {
  const { id } = useParams();
  const { data, loading, error, refetch } = useSubAgent(() => apiGet(`/api/drivers/${id}`), {
    topic: `driver_${id}_profile`,
  });

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  const identity = data.identity || {};
  const license = data.license || {};

  return (
    <div className="p-4 md:p-6 space-y-6">
      <Link to="/drivers" className="text-sm text-slate-400 hover:text-white">← Drivers</Link>
      <h1 className="text-2xl font-bold">{identity.full_name}</h1>
      <p className="text-slate-400">{identity.driver_code}</p>

      <div className="grid lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm font-semibold mb-3">License</h2>
          <p className="text-lg">
            <span className={`inline-block w-3 h-3 rounded-full mr-2 ${complianceColor(license.expiry_status)}`} />
            Class {license.license_class} · expires {formatDate(license.expiry_date)}
          </p>
          <p className="text-sm text-slate-400 mt-2">{license.days_remaining} days remaining</p>
          <p className="text-sm mt-2">Endorsements: {license.endorsements || "—"}</p>
          <p className="text-sm">#{license.number} ({license.state})</p>
        </section>

        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm font-semibold mb-3">Current Assignment</h2>
          {data.current_assignment ? (
            <div>
              <Link to={`/trucks/${data.current_assignment.truck_unit}`} className="text-blue-400 text-lg">
                Unit {data.current_assignment.truck_unit}
              </Link>
              <p className="text-sm text-slate-400">{data.current_assignment.truck_make_model_year}</p>
              <p className="text-sm">Since {formatDate(data.current_assignment.assigned_since)} ({data.current_assignment.days_assigned}d)</p>
            </div>
          ) : (
            <p className="text-slate-500">Unassigned</p>
          )}
        </section>
      </div>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-sm font-semibold mb-3">Assignment History</h2>
        <div className="flex flex-wrap gap-2">
          {(data.assignment_history || []).map((a, i) => (
            <div key={i} className="px-3 py-2 rounded bg-slate-800 text-xs">
              <span className="font-medium">Unit {a.truck_unit}</span>
              <br />
              {formatDate(a.start_date)} – {a.end_date ? formatDate(a.end_date) : "present"}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-sm font-semibold mb-3">Relationship Graph</h2>
        <GraphView data={data.relationships_graph} height={350} />
      </section>
    </div>
  );
}
