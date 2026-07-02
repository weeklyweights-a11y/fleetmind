export function formatCurrency(value) {
  const n = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

export function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatPercent(value) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Number(value).toFixed(1)}%`;
}

export function timeAgo(value) {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function complianceColor(status) {
  const map = {
    green: "bg-emerald-500",
    yellow: "bg-amber-500",
    red: "bg-red-500",
    grey: "bg-slate-500",
    compliant: "bg-emerald-500",
    attention_needed: "bg-amber-500",
    non_compliant: "bg-red-500",
    incomplete: "bg-slate-500",
  };
  return map[status] || "bg-slate-500";
}

export function statusBadgeClass(status) {
  const s = (status || "").toLowerCase();
  if (s === "complete" || s === "approved") return "bg-emerald-900/50 text-emerald-300";
  if (s === "needs_review") return "bg-amber-900/50 text-amber-300";
  if (s === "failed" || s === "rejected") return "bg-red-900/50 text-red-300";
  return "bg-slate-800 text-slate-300";
}
