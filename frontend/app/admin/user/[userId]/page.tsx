"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// ─── API ─────────────────────────────────────────────────────────────────────

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

// ─── Types ───────────────────────────────────────────────────────────────────

interface UserDetail {
  user: {
    user_id: string;
    email: string | null;
    name: string | null;
    tier: string;
    created_at: string | null;
    last_active: string | null;
  };
  subscription: {
    tier: string;
    strategic_queries_used: number;
    strategic_queries_limit: number;
    billing_period_start: string | null;
    billing_period_end: string | null;
  } | null;
  clients: {
    id: string;
    name: string;
    document_count: number;
    last_document_upload: string | null;
    query_count: number;
  }[];
  activity_timeline: {
    timestamp: string;
    endpoint: string | null;
    query_type: string;
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    cost: number;
    client_name: string | null;
  }[];
  daily_activity: {
    date: string;
    queries: number;
    documents_uploaded: number;
    cost: number;
  }[];
  documents: {
    total: number;
    processed: number;
    unprocessed: number;
    recent: {
      filename: string;
      upload_date: string | null;
      file_type: string;
      processed: boolean;
    }[];
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TIER_BADGE: Record<string, string> = {
  free: "bg-gray-100 text-gray-700",
  starter: "bg-blue-100 text-blue-700",
  professional: "bg-purple-100 text-purple-700",
  firm: "bg-amber-100 text-amber-700",
};

function tierBadge(tier: string, size: "sm" | "md" = "sm") {
  const cls = TIER_BADGE[tier] ?? "bg-gray-100 text-gray-600";
  const sizing = size === "md" ? "px-3 py-1 text-xs" : "px-2 py-0.5 text-[10px]";
  return (
    <span className={`inline-block rounded-full font-semibold uppercase ${sizing} ${cls}`}>
      {tier}
    </span>
  );
}

type HealthStatus = "active" | "idle" | "at_risk" | "new";

function getHealthStatus(
  lastActive: string | null,
  createdAt: string | null
): HealthStatus {
  const daysSinceActive = lastActive
    ? Math.floor((Date.now() - new Date(lastActive).getTime()) / 86400000)
    : null;
  const createdDaysAgo = createdAt
    ? Math.floor((Date.now() - new Date(createdAt).getTime()) / 86400000)
    : 999;

  if (createdDaysAgo <= 3 && daysSinceActive === null) return "new";
  if (daysSinceActive === null || daysSinceActive > 14) return "at_risk";
  if (daysSinceActive > 7) return "idle";
  return "active";
}

const HEALTH_DOT: Record<HealthStatus, string> = {
  active: "bg-green-500",
  idle: "bg-yellow-400",
  at_risk: "bg-red-400",
  new: "bg-gray-300",
};

const HEALTH_LABEL: Record<HealthStatus, string> = {
  active: "Active",
  idle: "Idle",
  at_risk: "At Risk",
  new: "New",
};

const HEALTH_TEXT: Record<HealthStatus, string> = {
  active: "text-green-700",
  idle: "text-yellow-700",
  at_risk: "text-red-700",
  new: "text-gray-500",
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

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function shortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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

function daysBetween(a: string, b: string): number {
  return Math.ceil(
    (new Date(b).getTime() - new Date(a).getTime()) / 86400000
  );
}

function accountAge(createdAt: string | null): string {
  if (!createdAt) return "";
  const days = Math.floor(
    (Date.now() - new Date(createdAt).getTime()) / 86400000
  );
  if (days === 0) return "today";
  if (days === 1) return "1 day";
  if (days < 30) return `${days} days`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month" : `${months} months`;
}

// ─── Page Component ──────────────────────────────────────────────────────────

export default function UserDetailPage() {
  const params = useParams();
  const userId = params.userId as string;

  const [data, setData] = useState<UserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activityPage, setActivityPage] = useState(0);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    apiFetch<UserDetail>(`/users/${userId}/detail`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load");
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (error) {
    return (
      <div className="px-8 py-8">
        <BackLink />
        <div className="mt-4 rounded-xl border border-red-200 bg-white p-8 text-center">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="px-8 py-8">
        <BackLink />
        <div className="mt-6 animate-pulse space-y-6">
          <div className="h-8 w-64 rounded bg-gray-200" />
          <div className="h-4 w-48 rounded bg-gray-200" />
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="rounded-xl border border-gray-200 bg-white p-5">
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

  const { user, subscription, clients, activity_timeline, daily_activity, documents } = data;
  const health = getHealthStatus(user.last_active, user.created_at);
  const totalQueries = activity_timeline.length; // from timeline; fallback
  const totalCost = activity_timeline.reduce((s, a) => s + a.cost, 0);
  const avgCostPerQuery = totalQueries > 0 ? totalCost / totalQueries : 0;
  const sortedClients = [...clients].sort((a, b) => b.query_count - a.query_count);

  // Activity feed pagination
  const PAGE_SIZE = 20;
  const totalPages = Math.ceil(activity_timeline.length / PAGE_SIZE);
  const pagedActivity = activity_timeline.slice(
    activityPage * PAGE_SIZE,
    (activityPage + 1) * PAGE_SIZE
  );

  // Subscription usage
  const quotaUsed = subscription?.strategic_queries_used ?? 0;
  const quotaLimit = subscription?.strategic_queries_limit ?? 0;
  const quotaPct = quotaLimit > 0 ? (quotaUsed / quotaLimit) * 100 : 0;
  const quotaColor =
    quotaPct >= 80 ? "bg-red-500" : quotaPct >= 60 ? "bg-yellow-400" : "bg-green-500";
  const daysRemaining =
    subscription?.billing_period_end
      ? Math.max(0, daysBetween(new Date().toISOString(), subscription.billing_period_end))
      : null;

  return (
    <div className="px-8 py-8 space-y-6">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <BackLink />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {user.name || user.email || user.user_id}
          </h1>
          {user.name && user.email && (
            <p className="mt-0.5 text-sm text-gray-500">{user.email}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500">
            {tierBadge(user.tier, "md")}
            <span className="flex items-center gap-1.5">
              <span className={`inline-block h-2 w-2 rounded-full ${HEALTH_DOT[health]}`} />
              <span className={HEALTH_TEXT[health]}>{HEALTH_LABEL[health]}</span>
            </span>
            {user.created_at && (
              <span>
                Member since {formatDate(user.created_at)} ({accountAge(user.created_at)})
              </span>
            )}
            <span className="group relative cursor-default">
              Last active: {relativeTime(user.last_active)}
              <span className="pointer-events-none absolute bottom-full left-0 mb-1.5 hidden whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-[10px] text-white shadow-lg group-hover:block z-10">
                {user.last_active ? formatDate(user.last_active) : "No activity recorded"}
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* ── Row 1: Key Metrics ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Clients" value={String(clients.length)} />
        <StatCard
          label="Documents"
          value={String(documents.total)}
          sub={`${documents.processed} processed, ${documents.unprocessed} pending`}
        />
        <StatCard
          label="Total Queries"
          value={String(totalQueries)}
        />
        <StatCard
          label="AI Cost"
          value={fmt$(totalCost)}
          sub={`avg ${fmt$(avgCostPerQuery, 4)} per query`}
        />
      </div>

      {/* ── Row 2: Activity Chart + Client Breakdown ────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* Daily Activity Chart */}
        <div className="lg:col-span-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Daily Activity (30 days)
          </h3>
          <div className="mt-4 h-56">
            {daily_activity.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={daily_activity}
                  margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                >
                  <defs>
                    <linearGradient id="queryGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="docGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
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
                    tick={{ fontSize: 10, fill: "#9ca3af" }}
                    axisLine={false}
                    tickLine={false}
                    width={32}
                    allowDecimals={false}
                  />
                  <Tooltip content={<ActivityTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="queries"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#queryGrad)"
                    name="Queries"
                  />
                  <Area
                    type="monotone"
                    dataKey="documents_uploaded"
                    stroke="#10b981"
                    strokeWidth={2}
                    fill="url(#docGrad)"
                    name="Documents"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-gray-400">
                No activity data for the last 30 days
              </div>
            )}
          </div>
          {/* Legend */}
          <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
              Queries
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
              Documents
            </span>
          </div>
        </div>

        {/* Client Usage Table */}
        <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
              Client Usage
            </h3>
          </div>
          {sortedClients.length === 0 ? (
            <div className="px-5 py-10 text-center text-xs text-gray-400">
              No clients
            </div>
          ) : (
            <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wider text-gray-400">
                    <th className="px-5 py-2">Client</th>
                    <th className="px-3 py-2 text-right">Docs</th>
                    <th className="px-3 py-2 text-right">Queries</th>
                    <th className="px-3 py-2">Last Upload</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedClients.map((c) => (
                    <tr key={c.id} className="border-b border-gray-50">
                      <td className="px-5 py-2 font-medium text-gray-900 truncate max-w-[160px]">
                        {c.name}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-700">
                        {c.document_count}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-700">
                        {c.query_count}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        {relativeTime(c.last_document_upload)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ── Row 3: Recent Activity Feed ─────────────────────────────── */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Recent Activity
          </h3>
          <span className="text-xs text-gray-400">
            {activity_timeline.length} entries
          </span>
        </div>

        {activity_timeline.length === 0 ? (
          <div className="px-5 py-10 text-center text-xs text-gray-400">
            No activity recorded
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wider text-gray-400">
                    <th className="px-5 py-2">Timestamp</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Client</th>
                    <th className="px-3 py-2">Model</th>
                    <th className="px-3 py-2 text-right">Tokens</th>
                    <th className="px-3 py-2 text-right">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedActivity.map((a, i) => (
                    <tr
                      key={`${a.timestamp}-${i}`}
                      className={`border-b border-gray-50 ${i % 2 === 1 ? "bg-gray-50/50" : ""}`}
                    >
                      <td className="px-5 py-2 text-xs text-gray-500 whitespace-nowrap">
                        <span className="group relative cursor-default">
                          {relativeTime(a.timestamp)}
                          <span className="pointer-events-none absolute bottom-full left-0 mb-1.5 hidden whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-[10px] text-white shadow-lg group-hover:block z-10">
                            {formatDateTime(a.timestamp)}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <TypeBadge endpoint={a.endpoint} queryType={a.query_type} />
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-700 truncate max-w-[140px]">
                        {a.client_name || "—"}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500 truncate max-w-[120px]">
                        {shortModelName(a.model)}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums text-gray-500">
                        {a.prompt_tokens.toLocaleString()} / {a.completion_tokens.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums text-gray-700">
                        {fmt$(a.cost, 4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-gray-100 px-5 py-2">
                <button
                  onClick={() => setActivityPage((p) => Math.max(0, p - 1))}
                  disabled={activityPage === 0}
                  className="rounded px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:text-gray-300 disabled:hover:bg-transparent"
                >
                  Prev
                </button>
                <span className="text-xs text-gray-400">
                  Page {activityPage + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setActivityPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={activityPage >= totalPages - 1}
                  className="rounded px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:text-gray-300 disabled:hover:bg-transparent"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Row 4: Subscription & Billing ───────────────────────────── */}
      {subscription && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Subscription &amp; Billing
          </h3>

          <div className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {/* Tier */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400">Current Tier</p>
              <div className="mt-1">{tierBadge(subscription.tier, "md")}</div>
            </div>

            {/* Strategic Queries */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400">
                Strategic Queries
              </p>
              <p className="mt-1 text-sm font-semibold text-gray-900">
                {quotaUsed} / {quotaLimit}
              </p>
              <div className="mt-1.5 h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${quotaColor}`}
                  style={{ width: `${Math.min(quotaPct, 100)}%` }}
                />
              </div>
              <p className="mt-0.5 text-[10px] text-gray-400">
                {Math.round(quotaPct)}% used
              </p>
            </div>

            {/* Billing Period */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400">
                Billing Period
              </p>
              <p className="mt-1 text-sm text-gray-900">
                {formatDate(subscription.billing_period_start)} —{" "}
                {formatDate(subscription.billing_period_end)}
              </p>
            </div>

            {/* Days Remaining */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400">
                Days Remaining
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {daysRemaining ?? "—"}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

function BackLink() {
  return (
    <Link
      href="/admin"
      className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 transition-colors hover:text-gray-900"
    >
      <svg
        className="h-3.5 w-3.5"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={2}
        stroke="currentColor"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
      </svg>
      Back to Dashboard
    </Link>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-gray-400">{sub}</p>}
    </div>
  );
}

function TypeBadge({
  endpoint,
  queryType,
}: {
  endpoint: string | null;
  queryType: string;
}) {
  // Determine display type from endpoint/query_type
  let label: string;
  let cls: string;
  if (endpoint === "classify" || queryType === "classification") {
    label = "Classify";
    cls = "bg-gray-100 text-gray-600";
  } else if (endpoint === "brief" || queryType === "brief") {
    label = "Brief";
    cls = "bg-indigo-50 text-indigo-600";
  } else if (queryType === "strategic") {
    label = "Strategic";
    cls = "bg-purple-50 text-purple-600";
  } else {
    label = "Query";
    cls = "bg-blue-50 text-blue-600";
  }
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>
      {label}
    </span>
  );
}

function ActivityTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-md text-xs">
      <p className="font-medium text-gray-900">{shortDate(d.date)}</p>
      <p className="text-blue-600">{d.queries} queries</p>
      <p className="text-emerald-600">{d.documents_uploaded} documents</p>
      <p className="text-gray-500">{fmt$(d.cost, 4)} cost</p>
    </div>
  );
}

function shortModelName(model: string): string {
  return model.replace(/-\d{8,}$/, "").replace(/-(\d)-(\d)$/, "-$1.$2");
}
