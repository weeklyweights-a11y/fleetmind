import { Link, useParams } from "react-router-dom";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
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
import { formatCurrency, formatDate } from "../utils/format.js";

export default function VendorDetail() {
  const { id } = useParams();
  const { data, loading, error, refetch } = useSubAgent(() => apiGet(`/api/vendors/${id}`));

  if (loading) return <div className="p-6"><Skeleton className="h-64" /></div>;
  if (error) return <div className="p-6"><ErrorPanel message={error} onRetry={refetch} /></div>;

  return (
    <div className="p-4 md:p-6 space-y-6">
      <Link to="/vendors" className="text-sm text-slate-400 hover:text-white">← Vendors</Link>
      <h1 className="text-2xl font-bold">{data.vendor?.name}</h1>
      <p className="text-slate-400">{data.vendor?.address}</p>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div className="rounded border border-slate-800 p-3">
          <p className="text-slate-500">Total Spend</p>
          <p className="text-xl font-bold">{formatCurrency(data.summary?.total_spend)}</p>
        </div>
        <div className="rounded border border-slate-800 p-3">
          <p className="text-slate-500">Events</p>
          <p className="text-xl font-bold">{data.summary?.event_count}</p>
        </div>
        <div className="rounded border border-slate-800 p-3">
          <p className="text-slate-500">Avg Cost</p>
          <p className="text-xl font-bold">{formatCurrency(data.summary?.avg_cost)}</p>
        </div>
      </div>

      {data.comparison && (
        <p className="text-sm text-slate-400">
          {data.comparison.difference_pct > 0 ? "↑" : "↓"} {Math.abs(data.comparison.difference_pct)}% vs fleet average
        </p>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm font-semibold mb-3">Spend Trend</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.trend || []}>
              <XAxis dataKey="month" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v) => formatCurrency(v)} />
              <Line type="monotone" dataKey="spend" stroke="#f97316" />
            </LineChart>
          </ResponsiveContainer>
        </section>
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm font-semibold mb-3">By Truck</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.by_truck || []}>
              <XAxis dataKey="truck_unit" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v) => formatCurrency(v)} />
              <Bar dataKey="total_spend" fill="#f97316" />
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-sm font-semibold mb-3">Relationship Graph</h2>
        <GraphView data={data.relationship_graph} height={350} />
      </section>

      <p className="text-xs text-slate-500">
        First visit: {formatDate(data.summary?.first_visit)} · Last: {formatDate(data.summary?.last_visit)}
      </p>
    </div>
  );
}
