"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useMemo, useState } from "react";

import { createAdminApi, type AdminUser, type AdminOverview } from "@/lib/api";

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
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${cls}`}>
      {tier}
    </span>
  );
}

type ActivityStatus = "active" | "idle" | "inactive" | "never";

function activityStatus(days: number | null): ActivityStatus {
  if (days === null) return "never";
  if (days <= 7) return "active";
  if (days <= 30) return "idle";
  return "inactive";
}

const STATUS_DOT: Record<ActivityStatus, string> = {
  active: "bg-green-500",
  idle: "bg-yellow-400",
  inactive: "bg-red-400",
  never: "bg-gray-300",
};

const STATUS_LABEL: Record<ActivityStatus, string> = {
  active: "Active",
  idle: "Idle",
  inactive: "Inactive",
  never: "Never",
};

const ROW_BG: Record<ActivityStatus, string> = {
  active: "bg-green-50/40",
  idle: "bg-yellow-50/30",
  inactive: "bg-red-50/20",
  never: "",
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

function fmt$(n: number, decimals = 2): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

type SortKey = "created_at" | "last_active_at" | "total_queries" | "tier";

const TIER_ORDER: Record<string, number> = { free: 0, starter: 1, professional: 2, firm: 3 };

// ─── Component ───────────────────────────────────────────────────────────────

export default function AdminDashboardPage() {
  const { getToken } = useAuth();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("created_at");

  useEffect(() => {
    let cancelled = false;
    const api = createAdminApi(getToken);

    Promise.all([api.users(), api.overview()])
      .then(([u, o]) => {
        if (!cancelled) {
          setUsers(u);
          setOverview(o);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });

    return () => { cancelled = true; };
  }, [getToken]);

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
      switch (sortBy) {
        case "last_active_at":
          return (b.last_active_at ?? "").localeCompare(a.last_active_at ?? "");
        case "total_queries":
          return b.total_queries - a.total_queries;
        case "tier":
          return (TIER_ORDER[b.tier] ?? 0) - (TIER_ORDER[a.tier] ?? 0);
        default:
          return b.created_at.localeCompare(a.created_at);
      }
    });
    return list;
  }, [users, search, sortBy]);

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
        <MetricCard label="Documents" value={String(overview.total_documents)} />
        <MetricCard label="Queries Today" value={String(overview.total_queries_today)} />
        <MetricCard label="AI Cost MTD" value={fmt$(overview.total_revenue_mtd)} />
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
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-700 focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-200"
          >
            <option value="created_at">Signup date</option>
            <option value="last_active_at">Last active</option>
            <option value="total_queries">Query count</option>
            <option value="tier">Tier</option>
          </select>
          <span className="ml-auto text-xs text-gray-400">
            {filtered.length} user{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>

        {filtered.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <p className="text-sm text-gray-400">
              {users.length === 0
                ? "No users yet — start outreach to get your first sign-ups!"
                : "No users match your search."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wider text-gray-400">
                  <th className="px-5 py-3">User</th>
                  <th className="px-3 py-3">Tier</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Clients</th>
                  <th className="px-3 py-3 text-right">Docs</th>
                  <th className="px-3 py-3 text-right">Queries (7d)</th>
                  <th className="px-3 py-3 text-right">Total Queries</th>
                  <th className="px-3 py-3 text-right">AI Cost</th>
                  <th className="px-3 py-3">Last Active</th>
                  <th className="px-3 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => {
                  const status = activityStatus(u.days_since_active);
                  return (
                    <tr
                      key={u.user_id}
                      className={`border-b border-gray-50 ${ROW_BG[status]}`}
                    >
                      <td className="px-5 py-3">
                        <div className="font-medium text-gray-900">
                          {u.user_name || "—"}
                        </div>
                        <div className="text-xs text-gray-400">
                          {u.user_email || u.user_id}
                        </div>
                      </td>
                      <td className="px-3 py-3">{tierBadge(u.tier)}</td>
                      <td className="px-3 py-3">
                        <span className="flex items-center gap-1.5">
                          <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[status]}`} />
                          <span className="text-xs text-gray-600">{STATUS_LABEL[status]}</span>
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
                      <td className="px-3 py-3 text-right tabular-nums text-gray-700">
                        {fmt$(u.total_cost)}
                      </td>
                      <td className="px-3 py-3 text-xs text-gray-500">
                        {relativeTime(u.last_active_at)}
                      </td>
                      <td className="px-3 py-3">
                        <Link
                          href={`/dashboard/admin/users/${u.user_id}`}
                          className="text-xs font-medium text-blue-600 hover:text-blue-800"
                        >
                          View
                        </Link>
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
