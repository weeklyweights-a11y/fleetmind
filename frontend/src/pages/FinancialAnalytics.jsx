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
  Legend,
} from "recharts";
import { apiGet } from "../api/client.js";
import { useSubAgent } from "../hooks/useSubAgent.js";
import { Skeleton } from "../components/common/Skeleton.jsx";
import { ErrorPanel } from "../components/common/ErrorPanel.jsx";
import { formatCurrency } from "../utils/format.js";

const COLORS = ["#3b82f6", "#22c55e", "#f97316", "#a855f7", "#ef4444", "#06b6d4"];

function vendorChartData(vendors) {
  return (vendors || [])
    .map((v) => ({
      name: v.name,
      total_spend: Number(v.total_spend) || 0,
    }))
    .filter((v) => v.total_spend > 0)
    .sort((a, b) => b.total_spend - a.total_spend)
    .slice(0, 8);
}

export default function FinancialAnalytics() {
  const comparison = useSubAgent(() => apiGet("/api/fleet/comparison"), { topic: "fleet_stats" });
  const summary = useSubAgent(() => apiGet("/api/fleet/maintenance-summary"), { topic: "fleet_stats" });
  const vendors = useSubAgent(() => apiGet("/api/vendors"), { topic: "fleet_stats" });

  if (comparison.loading) return <div className="p-6"><Skeleton className="h-64" /></div>;

  return (
    <div className="p-4 md:p-6 space-y-6">
      <h1 className="text-xl font-bold">Financial Analytics</h1>

      {comparison.error && <ErrorPanel message={comparison.error} onRetry={comparison.refetch} />}

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-sm font-semibold mb-3">Cost Comparison by Truck</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={(comparison.data?.trucks || []).slice(0, 16).map((t) => ({
              ...t,
              tco: Number(t.tco) || 0,
              maintenance_spend: Number(t.maintenance_spend) || 0,
            }))}
          >
            <XAxis dataKey="unit_number" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v) => formatCurrency(v)} />
            <Legend />
            <Bar dataKey="tco" name="TCO" fill="#3b82f6" />
            <Bar dataKey="maintenance_spend" name="Maintenance" fill="#22c55e" />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <div className="grid lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm font-semibold mb-3">Monthly Cost Trend</h2>
          {summary.loading ? <Skeleton className="h-48" /> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart
                data={(summary.data?.monthly_trend || []).map((p) => ({
                  ...p,
                  spend: Number(p.spend) || 0,
                }))}
              >
                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => formatCurrency(v)} />
                <Line type="monotone" dataKey="spend" stroke="#3b82f6" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="rounded-lg border border-slate-800 p-4">
          <h2 className="text-sm font-semibold mb-3">Category Breakdown</h2>
          {summary.loading ? <Skeleton className="h-48" /> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={(summary.data?.by_category || []).map((p) => ({
                  ...p,
                  spend: Number(p.spend) || 0,
                }))}
              >
                <XAxis dataKey="category" tick={{ fontSize: 9 }} angle={-20} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => formatCurrency(v)} />
                <Bar dataKey="spend" fill="#22c55e" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>
      </div>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-sm font-semibold mb-3">Vendor Spend</h2>
        {vendors.loading ? (
          <Skeleton className="h-48" />
        ) : vendors.error ? (
          <ErrorPanel message={vendors.error} onRetry={vendors.refetch} />
        ) : (
          <>
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={vendorChartData(vendors.data?.vendors)}
                    dataKey="total_spend"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={({ name, percent }) =>
                      percent > 0.05 ? `${name.slice(0, 18)} ${(percent * 100).toFixed(0)}%` : ""
                    }
                    labelLine={false}
                  >
                    {vendorChartData(vendors.data?.vendors).map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(v)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {vendorChartData(vendors.data?.vendors).length === 0 && (
              <p className="text-sm text-slate-500 text-center">No vendor spend data</p>
            )}
          </>
        )}
        {vendors.data?.concentration?.top_vendor_pct > 50 && (
          <p className="text-amber-400 text-sm mt-2">
            Warning: top vendor accounts for {vendors.data.concentration.top_vendor_pct}% of spend
          </p>
        )}
      </section>
    </div>
  );
}
