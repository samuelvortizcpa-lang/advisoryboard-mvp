"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// ─── API types ───────────────────────────────────────────────────────────────

interface AdminUser {
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  tier: string;
  stripe_status: string | null;
  payment_status: string | null;
  created_at: string;
  client_count: number;
  document_count: number;
  total_queries: number;
  total_cost: number;
  last_active_at: string | null;
  days_since_active: number | null;
  queries_last_7_days: number;
  storage_used_mb: number;
}

interface AdminOverview {
  total_users: number;
  total_users_by_tier: Record<string, number>;
  active_last_7_days: number;
  active_last_30_days: number;
  total_revenue_mtd: number;
  total_documents: number;
  total_queries_today: number;
  mrr: number;
}

interface ConversionFunnel {
  by_tier: Record<string, number>;
  total_users: number;
  paid_users: number;
  conversion_rate: number;
  average_days_to_upgrade: number | null;
  recently_hit_limits: {
    user_id: string;
    email: string | null;
    name: string | null;
    tier: string;
    limits_hit: string[];
  }[];
}

interface MrrDataPoint {
  date: string;
  mrr: number;
  user_count: number;
  paid_count: number;
}

interface AiCostsData {
  daily_costs: {
    date: string;
    total_cost: number;
    by_model: Record<string, number>;
  }[];
  per_user_costs: {
    user_id: string;
    email: string | null;
    name: string | null;
    tier: string;
    total_cost: number;
    query_count: number;
    avg_cost_per_query: number;
  }[];
  total_cost: number;
  projected_monthly: number;
  top_expensive_queries: {
    timestamp: string;
    user_email: string | null;
    client_name: string | null;
    model: string;
    endpoint: string | null;
    prompt_tokens: number;
    completion_tokens: number;
    cost: number;
  }[];
}

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`/api/admin${path}`);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  free: "bg-gray-100 text-gray-700",
  starter: "bg-blue-100 text-blue-700",
  professional: "bg-purple-100 text-purple-700",
  firm: "bg-indigo-100 text-indigo-700",
};

function tierBadge(tier: string) {
  const cls = TIER_COLORS[tier] ?? "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${cls}`}
    >
      {tier}
    </span>
  );
}

type HealthStatus = "active" | "idle" | "at_risk" | "new";

function healthStatus(user: AdminUser): HealthStatus {
  const days = user.days_since_active;
  const createdDaysAgo = Math.floor(
    (Date.now() - new Date(user.created_at).getTime()) / 86400000
  );

  if (createdDaysAgo <= 3 && days === null) return "new";
  if (days === null || days > 14) return "at_risk";
  if (days > 7) return "idle";
  return "active";
}

const STATUS_DOT: Record<HealthStatus, string> = {
  active: "bg-green-500",
  idle: "bg-yellow-400",
  at_risk: "bg-red-400",
  new: "bg-gray-300",
};

const STATUS_LABEL: Record<HealthStatus, string> = {
  active: "Active",
  idle: "Idle",
  at_risk: "At Risk",
  new: "New",
};

const HEALTH_PRIORITY: Record<HealthStatus, number> = {
  at_risk: 0,
  idle: 1,
  new: 2,
  active: 3,
};

const ROW_BG: Record<HealthStatus, string> = {
  active: "bg-green-50/40",
  idle: "bg-yellow-50/30",
  at_risk: "bg-red-50/20",
  new: "",
};

function relativeTime(isoDate: string | null): string {
  if (!isoDate) return "Never";
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function formatDateTime(isoDate: string | null): string {
  if (!isoDate) return "No activity recorded";
  return new Date(isoDate).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function fmt$(n: number, decimals = 2): string {
  return (
    "$" +
    n.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
  );
}

function shortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

type SortKey =
  | "status"
  | "tier"
  | "last_active_at"
  | "document_count"
  | "queries_last_7_days"
  | "total_cost"
  | "created_at"
  | "total_queries";

const TIER_ORDER: Record<string, number> = {
  free: 0,
  starter: 1,
  professional: 2,
  firm: 3,
};

// Palette for model colors in the AI cost chart
const MODEL_COLORS = [
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ef4444", // red
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#f97316", // orange
  "#ec4899", // pink
];

// ─── Component ───────────────────────────────────────────────────────────────

export default function AdminDashboardPage() {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [funnel, setFunnel] = useState<ConversionFunnel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("status");
  const [sortAsc, setSortAsc] = useState(true);

  // Chart data
  const [mrrData, setMrrData] = useState<MrrDataPoint[] | null>(null);
  const [mrrDays, setMrrDays] = useState(30);
  const [aiCosts, setAiCosts] = useState<AiCostsData | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [u, o, f] = await Promise.all([
          apiFetch<AdminUser[]>("/users"),
          apiFetch<AdminOverview>("/overview"),
          apiFetch<ConversionFunnel>("/conversion-funnel").catch(
            () => null
          ),
        ]);
        if (!cancelled) {
          setUsers(u);
          setOverview(o);
          setFunnel(f);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch MRR data (re-fetches when mrrDays changes)
  useEffect(() => {
    let cancelled = false;
    apiFetch<MrrDataPoint[]>(`/mrr-history?days=${mrrDays}`)
      .then((d) => { if (!cancelled) setMrrData(d); })
      .catch(() => { if (!cancelled) setMrrData(null); });
    return () => { cancelled = true; };
  }, [mrrDays]);

  // Fetch AI costs once
  useEffect(() => {
    let cancelled = false;
    apiFetch<AiCostsData>("/ai-costs?days=30")
      .then((d) => { if (!cancelled) setAiCosts(d); })
      .catch(() => { if (!cancelled) setAiCosts(null); });
    return () => { cancelled = true; };
  }, []);

  // Compute max cost across users for the relative bar
  const maxUserCost = useMemo(() => {
    if (!users) return 0;
    return Math.max(...users.map((u) => u.total_cost), 0);
  }, [users]);

  // Threshold: cost is "high" if it's more than 3x the median non-zero cost
  const highCostThreshold = useMemo(() => {
    if (!users) return Infinity;
    const costs = users.map((u) => u.total_cost).filter((c) => c > 0).sort((a, b) => a - b);
    if (costs.length === 0) return Infinity;
    const median = costs[Math.floor(costs.length / 2)];
    return median * 3;
  }, [users]);

  const filtered = useMemo(() => {
    if (!users) return [];
    let list = users;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (u) =>
          (u.user_name ?? "").toLowerCase().includes(q) ||
          (u.user_email ?? "").toLowerCase().includes(q)
      );
    }
    list = [...list].sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case "status": {
          const aPri = HEALTH_PRIORITY[healthStatus(a)];
          const bPri = HEALTH_PRIORITY[healthStatus(b)];
          cmp = aPri - bPri;
          if (cmp === 0) {
            cmp = (b.last_active_at ?? "").localeCompare(a.last_active_at ?? "");
          }
          break;
        }
        case "tier":
          cmp = (TIER_ORDER[a.tier] ?? 0) - (TIER_ORDER[b.tier] ?? 0);
          break;
        case "last_active_at":
          cmp = (a.last_active_at ?? "").localeCompare(b.last_active_at ?? "");
          break;
        case "document_count":
          cmp = a.document_count - b.document_count;
          break;
        case "queries_last_7_days":
          cmp = a.queries_last_7_days - b.queries_last_7_days;
          break;
        case "total_cost":
          cmp = a.total_cost - b.total_cost;
          break;
        case "total_queries":
          cmp = a.total_queries - b.total_queries;
          break;
        default:
          cmp = a.created_at.localeCompare(b.created_at);
      }
      return sortAsc ? cmp : -cmp;
    });
    return list;
  }, [users, search, sortBy, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortBy(key);
      setSortAsc(key === "status");
    }
  }

  if (error) {
    return (
      <div className="px-8 py-8">
        <div className="rounded-xl border border-red-200 bg-white p-8 text-center">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!users || !overview) {
    return (
      <div className="px-8 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-6 w-48 rounded bg-gray-200" />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-gray-200 bg-white p-5"
              >
                <div className="h-3 w-16 rounded bg-gray-200" />
                <div className="mt-3 h-7 w-20 rounded bg-gray-200" />
              </div>
            ))}
          </div>
          <div className="h-64 rounded-xl border border-gray-200 bg-white" />
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-8 space-y-6">
      {/* Header */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Admin
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">
          Platform Dashboard
        </h1>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Total Users" value={String(overview.total_users)} />
        <MetricCard label="MRR" value={fmt$(overview.mrr, 0)} />
        <MetricCard
          label="Active (7d)"
          value={`${overview.active_last_7_days} / ${overview.total_users}`}
        />
        <MetricCard
          label="Documents"
          value={String(overview.total_documents)}
        />
        <MetricCard
          label="Queries Today"
          value={String(overview.total_queries_today)}
        />
        <MetricCard
          label="AI Cost MTD"
          value={fmt$(overview.total_revenue_mtd)}
        />
      </div>

      {/* Conversion funnel card */}
      {funnel && <ConversionFunnelCard funnel={funnel} />}

      {/* MRR + AI Cost charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <MrrChartCard
          data={mrrData}
          currentMrr={overview.mrr}
          days={mrrDays}
          onDaysChange={setMrrDays}
        />
        <AiCostChartCard data={aiCosts} />
      </div>

      {/* User health table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        {/* Table toolbar */}
        <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-5 py-3">
          <input
            type="text"
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64 rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-700 placeholder:text-gray-400 focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-200"
          />
          <span className="ml-auto text-xs text-gray-400">
            {filtered.length} user{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>

        {filtered.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <p className="text-sm text-gray-400">
              {users.length === 0
                ? "No users yet \u2014 start outreach to get your first sign-ups!"
                : "No users match your search."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wider text-gray-400">
                  <th className="px-5 py-3">User</th>
                  <SortTh label="Tier" sortKey="tier" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} />
                  <SortTh label="Status" sortKey="status" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} />
                  <th className="px-3 py-3 text-right">Clients</th>
                  <SortTh label="Docs" sortKey="document_count" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} align="right" />
                  <SortTh label="Queries (7d)" sortKey="queries_last_7_days" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} align="right" />
                  <SortTh label="Total Queries" sortKey="total_queries" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} align="right" />
                  <SortTh label="AI Cost" sortKey="total_cost" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} align="right" />
                  <SortTh label="Last Active" sortKey="last_active_at" currentSort={sortBy} asc={sortAsc} onSort={toggleSort} />
                  <th className="w-8 px-2 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => {
                  const status = healthStatus(u);
                  const isHighCost = u.total_cost > highCostThreshold && u.total_cost > 0;
                  const barPct = maxUserCost > 0 ? (u.total_cost / maxUserCost) * 100 : 0;
                  const avgCostPerQuery = u.total_queries > 0 ? u.total_cost / u.total_queries : 0;
                  return (
                    <tr
                      key={u.user_id}
                      onClick={() => router.push(`/admin/user/${u.user_id}`)}
                      className={`border-b border-gray-50 cursor-pointer transition-colors hover:bg-blue-50/60 ${isHighCost ? "bg-amber-50/40" : ROW_BG[status]}`}
                    >
                      <td className="px-5 py-3">
                        {u.user_name ? (
                          <>
                            <div className="font-medium text-gray-900">
                              {u.user_name}
                            </div>
                            <div className="text-xs text-gray-400">
                              {u.user_email || u.user_id}
                            </div>
                          </>
                        ) : (
                          <div className="font-medium text-gray-900">
                            {u.user_email || u.user_id}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3">{tierBadge(u.tier)}</td>
                      <td className="px-3 py-3">
                        <span className="group relative flex items-center gap-1.5 cursor-default">
                          <span
                            className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[status]}`}
                          />
                          <span className="text-xs text-gray-600">
                            {STATUS_LABEL[status]}
                          </span>
                          <span className="pointer-events-none absolute bottom-full left-0 mb-1.5 hidden whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-[10px] text-white shadow-lg group-hover:block z-10">
                            {formatDateTime(u.last_active_at)}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-gray-700">
                        {u.client_count}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-gray-700">
                        {u.document_count}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-gray-700">
                        {u.queries_last_7_days}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-gray-700">
                        {u.total_queries}
                      </td>
                      <td className="px-3 py-3">
                        <div className="group relative flex flex-col items-end gap-1 cursor-default">
                          <span className={`tabular-nums ${isHighCost ? "font-semibold text-amber-700" : "text-gray-700"}`}>
                            {fmt$(u.total_cost)}
                          </span>
                          {/* Mini relative bar */}
                          <div className="h-1 w-16 rounded-full bg-gray-100 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${isHighCost ? "bg-amber-400" : "bg-blue-400"}`}
                              style={{ width: `${Math.max(barPct, barPct > 0 ? 2 : 0)}%` }}
                            />
                          </div>
                          {/* Tooltip */}
                          <span className="pointer-events-none absolute bottom-full right-0 mb-1.5 hidden whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-[10px] text-white shadow-lg group-hover:block z-10">
                            {u.total_queries} queries, avg {fmt$(avgCostPerQuery, 4)}/query
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-xs text-gray-500">
                        {relativeTime(u.last_active_at)}
                      </td>
                      <td className="w-8 px-2 py-3 text-gray-300">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function SortTh({
  label,
  sortKey,
  currentSort,
  asc,
  onSort,
  align,
}: {
  label: string;
  sortKey: SortKey;
  currentSort: SortKey;
  asc: boolean;
  onSort: (key: SortKey) => void;
  align?: "right";
}) {
  const active = currentSort === sortKey;
  const arrow = active ? (asc ? " \u2191" : " \u2193") : "";
  return (
    <th
      className={`px-3 py-3 cursor-pointer select-none transition-colors hover:text-gray-600 ${
        align === "right" ? "text-right" : ""
      } ${active ? "text-gray-600" : ""}`}
      onClick={() => onSort(sortKey)}
    >
      {label}
      {arrow}
    </th>
  );
}

// ─── MRR Chart Card ─────────────────────────────────────────────────────────

function MrrChartCard({
  data,
  currentMrr,
  days,
  onDaysChange,
}: {
  data: MrrDataPoint[] | null;
  currentMrr: number;
  days: number;
  onDaysChange: (d: number) => void;
}) {
  return (
    <div className="lg:col-span-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Monthly Recurring Revenue
          </h3>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {fmt$(currentMrr, 0)}
          </p>
        </div>
        <div className="flex rounded-lg border border-gray-200 text-xs">
          {([30, 60, 90] as const).map((d) => (
            <button
              key={d}
              onClick={() => onDaysChange(d)}
              className={`px-2.5 py-1 transition-colors ${
                days === d
                  ? "bg-gray-900 text-white"
                  : "text-gray-500 hover:text-gray-700"
              } ${d === 30 ? "rounded-l-lg" : ""} ${d === 90 ? "rounded-r-lg" : ""}`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 h-52">
        {data && data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="mrrGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#14b8a6" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#14b8a6" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={(v: number) => `$${v}`}
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip content={<MrrTooltip />} />
              <Area
                type="monotone"
                dataKey="mrr"
                stroke="#14b8a6"
                strokeWidth={2}
                fill="url(#mrrGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-gray-400">
            {data === null ? "Unable to load MRR data" : "No data available"}
          </div>
        )}
      </div>
    </div>
  );
}

function MrrTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as MrrDataPoint;
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-md text-xs">
      <p className="font-medium text-gray-900">{shortDate(d.date)}</p>
      <p className="text-teal-600 font-semibold">{fmt$(d.mrr, 0)} MRR</p>
      <p className="text-gray-500">{d.user_count} users ({d.paid_count} paid)</p>
    </div>
  );
}

// ─── AI Cost Chart Card ─────────────────────────────────────────────────────

function AiCostChartCard({ data }: { data: AiCostsData | null }) {
  const { chartData, models } = useMemo(() => {
    if (!data) return { chartData: [], models: [] as string[] };
    const modelSet = new Set<string>();
    for (const day of data.daily_costs) {
      for (const m of Object.keys(day.by_model)) modelSet.add(m);
    }
    const models = Array.from(modelSet);
    const chartData = data.daily_costs.map((day) => {
      const row: Record<string, any> = { date: day.date, total_cost: day.total_cost };
      for (const m of models) row[m] = day.by_model[m] ?? 0;
      return row;
    });
    return { chartData, models };
  }, [data]);

  const totalCost = data?.total_cost ?? 0;
  const projected = data?.projected_monthly ?? 0;
  const totalQueries = data
    ? data.per_user_costs.reduce((s, u) => s + u.query_count, 0)
    : 0;
  const avgPerQuery = totalQueries > 0 ? totalCost / totalQueries : 0;
  const mostExpensiveModel = data
    ? getMostExpensiveModel(data.daily_costs)
    : null;

  return (
    <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          AI Costs
        </h3>
        <p className="mt-1 text-2xl font-bold text-gray-900">
          ~{fmt$(projected, 2)}<span className="text-sm font-normal text-gray-400">/mo projected</span>
        </p>
      </div>

      <div className="mt-4 h-40">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                {models.map((m, i) => (
                  <linearGradient key={m} id={`costGrad-${i}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={MODEL_COLORS[i % MODEL_COLORS.length]} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={MODEL_COLORS[i % MODEL_COLORS.length]} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip content={<AiCostTooltip models={models} />} />
              {models.map((m, i) => (
                <Area
                  key={m}
                  type="monotone"
                  dataKey={m}
                  stackId="1"
                  stroke={MODEL_COLORS[i % MODEL_COLORS.length]}
                  strokeWidth={1.5}
                  fill={`url(#costGrad-${i})`}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-gray-400">
            {data === null ? "Unable to load cost data" : "No cost data yet"}
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 border-t border-gray-100 pt-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-gray-400">Total</p>
          <p className="text-sm font-semibold text-gray-900">{fmt$(totalCost)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-gray-400">Avg/Query</p>
          <p className="text-sm font-semibold text-gray-900">{fmt$(avgPerQuery, 4)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-gray-400">Top Model</p>
          <p className="text-sm font-semibold text-gray-900 truncate" title={mostExpensiveModel ?? "—"}>
            {mostExpensiveModel ? shortModelName(mostExpensiveModel) : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}

function AiCostTooltip({ active, payload, models }: any) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-md text-xs max-w-xs">
      <p className="font-medium text-gray-900">{shortDate(row.date)}</p>
      <p className="font-semibold text-gray-700 mt-0.5">{fmt$(row.total_cost, 4)} total</p>
      {(models as string[]).map((m: string, i: number) => {
        const val = row[m];
        if (!val || val === 0) return null;
        return (
          <div key={m} className="flex items-center gap-1.5 mt-0.5">
            <span
              className="inline-block h-2 w-2 rounded-full shrink-0"
              style={{ backgroundColor: MODEL_COLORS[i % MODEL_COLORS.length] }}
            />
            <span className="text-gray-500 truncate">{shortModelName(m)}</span>
            <span className="ml-auto text-gray-700 tabular-nums">{fmt$(val, 4)}</span>
          </div>
        );
      })}
    </div>
  );
}

function getMostExpensiveModel(
  dailyCosts: { by_model: Record<string, number> }[]
): string | null {
  const totals: Record<string, number> = {};
  for (const day of dailyCosts) {
    for (const [m, cost] of Object.entries(day.by_model)) {
      totals[m] = (totals[m] ?? 0) + cost;
    }
  }
  let best: string | null = null;
  let bestCost = 0;
  for (const [m, c] of Object.entries(totals)) {
    if (c > bestCost) {
      best = m;
      bestCost = c;
    }
  }
  return best;
}

function shortModelName(model: string): string {
  return model.replace(/-\d{8,}$/, "").replace(/-(\d)-(\d)$/, "-$1.$2");
}

// ─── Conversion Funnel ──────────────────────────────────────────────────────

const FUNNEL_TIER_COLORS: Record<string, string> = {
  free: "bg-gray-300",
  starter: "bg-blue-500",
  professional: "bg-purple-500",
  firm: "bg-amber-500",
};

const FUNNEL_TIER_DOT: Record<string, string> = {
  free: "bg-gray-300",
  starter: "bg-blue-500",
  professional: "bg-purple-500",
  firm: "bg-amber-500",
};

const LIMIT_LABELS: Record<string, string> = {
  strategic_queries: "Query limit",
  clients: "Client limit",
};

function ConversionFunnelCard({ funnel }: { funnel: ConversionFunnel }) {
  const tiers = ["free", "starter", "professional", "firm"] as const;
  const total = funnel.total_users || 1;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Tier Distribution
          </h3>
          <div className="mt-3 flex h-4 w-full overflow-hidden rounded-full bg-gray-100">
            {tiers.map((t) => {
              const count = funnel.by_tier[t] ?? 0;
              const pct = (count / total) * 100;
              if (pct === 0) return null;
              return (
                <div
                  key={t}
                  className={`${FUNNEL_TIER_COLORS[t]} transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${t}: ${count} (${Math.round(pct)}%)`}
                />
              );
            })}
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
            {tiers.map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${FUNNEL_TIER_DOT[t]}`}
                />
                <span className="capitalize">{t}:</span>
                <span className="font-medium text-gray-700">
                  {funnel.by_tier[t] ?? 0}
                </span>
              </span>
            ))}
          </div>
          <div className="mt-4 flex items-baseline gap-3">
            <span className="text-2xl font-bold text-gray-900">
              {funnel.conversion_rate}%
            </span>
            <span className="text-xs text-gray-400">
              conversion rate ({funnel.paid_users} paid / {funnel.total_users}{" "}
              total)
            </span>
          </div>
          {funnel.average_days_to_upgrade !== null && (
            <p className="mt-1 text-xs text-gray-400">
              Avg {funnel.average_days_to_upgrade} days to upgrade
            </p>
          )}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
              Upgrade Candidates
            </h3>
            {funnel.recently_hit_limits.length > 0 && (
              <span className="inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-100 px-1.5 text-[10px] font-semibold text-red-700">
                {funnel.recently_hit_limits.length}
              </span>
            )}
          </div>
          {funnel.recently_hit_limits.length === 0 ? (
            <p className="mt-3 text-xs text-gray-400">
              No users near limits
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {funnel.recently_hit_limits.slice(0, 5).map((u) => (
                <div
                  key={u.user_id}
                  className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-900">
                      {u.name || u.email || u.user_id}
                    </p>
                    {u.name && u.email && (
                      <p className="truncate text-xs text-gray-400">
                        {u.email}
                      </p>
                    )}
                  </div>
                  <div className="ml-3 flex items-center gap-2 shrink-0">
                    {tierBadge(u.tier)}
                    <div className="flex gap-1">
                      {u.limits_hit.map((l) => (
                        <span
                          key={l}
                          className="rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-medium text-red-600"
                        >
                          {LIMIT_LABELS[l] ?? l}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
              {funnel.recently_hit_limits.length > 5 && (
                <p className="text-xs text-gray-400 pl-3">
                  +{funnel.recently_hit_limits.length - 5} more
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
