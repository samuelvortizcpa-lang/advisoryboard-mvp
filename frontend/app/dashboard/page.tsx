"use client";

import Link from "next/link";
import { useAuth, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { createDashboardApi, type DashboardSummary } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import StatCard from "@/components/ui/StatCard";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import SectionCard from "@/components/ui/SectionCard";
import PriorityDot from "@/components/ui/PriorityDot";
import MemberRow from "@/components/ui/MemberRow";

type TimeRange = "7d" | "30d" | "90d";

const RANGE_DAYS: Record<TimeRange, number> = { "7d": 7, "30d": 30, "90d": 90 };

const DIST_COLORS: Record<string, string> = {
  "Quick Lookup": "#3B82F6",
  "Deep Analysis": "#8B5CF6",
  Brief: "#14B8A6",
  "Action Items": "#F59E0B",
  Other: "#D1D5DB",
};

export default function DashboardPage() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const { activeOrg } = useOrg();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");

  const load = useCallback(
    async (range: TimeRange) => {
      try {
        const api = createDashboardApi(getToken, activeOrg?.id);
        const result = await api.summary(RANGE_DAYS[range]);
        setData(result);
      } catch {
        // non-fatal — keep stale data or null
      }
    },
    [getToken, activeOrg?.id],
  );

  useEffect(() => {
    load(timeRange);
  }, [load, timeRange]);

  const handleTimeRangeChange = (range: TimeRange) => {
    setTimeRange(range);
  };

  const initials =
    ((user?.firstName?.[0] ?? "") + (user?.lastName?.[0] ?? "")).toUpperCase() ||
    "U";

  // ── Loading skeleton ───────────────────────────────────────────────────

  if (!data) {
    return (
      <div>
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">Overview</h1>
          <div className="flex items-center gap-3">
            <div className="h-9 w-28 animate-pulse rounded-lg bg-gray-200" />
            <div className="h-7 w-7 animate-pulse rounded-full bg-gray-200" />
          </div>
        </div>
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="animate-pulse rounded-lg bg-gray-50 p-4">
              <div className="h-3 w-16 rounded bg-gray-200" />
              <div className="mt-2 h-7 w-12 rounded bg-gray-200" />
              <div className="mt-2 h-3 w-20 rounded bg-gray-100" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
          <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 lg:col-span-3">
            <div className="h-4 w-24 rounded bg-gray-200" />
            <div className="mt-4 h-[240px] rounded bg-gray-50" />
          </div>
          <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 lg:col-span-2">
            <div className="h-4 w-32 rounded bg-gray-200" />
            <div className="mt-4 h-[240px] rounded bg-gray-50" />
          </div>
        </div>
      </div>
    );
  }

  // ── Computed values ────────────────────────────────────────────────────

  const { stats } = data;
  const queryPct =
    stats.ai_queries.limit > 0
      ? (stats.ai_queries.used / stats.ai_queries.limit) * 100
      : 0;

  const chartData = data.activity_chart.map((p) => ({
    date: p.date,
    value: p.queries,
  }));

  const donutData = data.query_distribution.map((d) => ({
    name: d.type,
    value: d.count,
    color: DIST_COLORS[d.type] ?? DIST_COLORS.Other,
  }));

  const totalQueries = data.query_distribution.reduce(
    (sum, d) => sum + d.count,
    0,
  );

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Top bar */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">Overview</h1>
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard/clients/new"
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            + New client
          </Link>
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-[11px] font-medium text-blue-700">
            {initials}
          </div>
        </div>
      </div>

      {/* Row 1: Stat cards */}
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Active clients"
          value={stats.clients.count}
          context={
            stats.clients.limit != null
              ? `of ${stats.clients.limit}`
              : undefined
          }
          contextType="muted"
        />
        <StatCard
          label="Action items"
          value={stats.action_items.pending}
          context={
            stats.action_items.overdue > 0
              ? `${stats.action_items.overdue} overdue`
              : "All on track"
          }
          contextType={stats.action_items.overdue > 0 ? "warning" : "success"}
        />
        <StatCard
          label="Documents"
          value={stats.documents.count}
          context={
            stats.documents.limit != null
              ? `of ${stats.documents.limit}`
              : undefined
          }
          contextType="muted"
        />
        <StatCard
          label="AI queries"
          value={stats.ai_queries.used}
          context={`of ${stats.ai_queries.limit}`}
          contextType={
            queryPct > 80 ? "warning" : "muted"
          }
        />
      </div>

      {/* Row 2: Charts */}
      <div className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <AreaChartCard
            title="Activity"
            data={chartData}
            timeRange={timeRange}
            onTimeRangeChange={handleTimeRangeChange}
          />
        </div>
        <div className="lg:col-span-2">
          <DonutChartCard
            title="Query distribution"
            data={donutData}
            centerValue={totalQueries}
            centerLabel="queries"
          />
        </div>
      </div>

      {/* Row 3: Content cards */}
      <div className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* Needs attention */}
        <SectionCard
          title="Needs attention"
          action={{ label: "View all", href: "/dashboard/actions" }}
        >
          {data.attention_items.length === 0 ? (
            <div className="flex items-center gap-2 py-2">
              <svg className="h-4 w-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm text-gray-500">All caught up</span>
            </div>
          ) : (
            <div>
              {data.attention_items.slice(0, 5).map((item) => (
                <div
                  key={item.id}
                  className="flex items-start gap-2.5 border-b border-gray-100 py-2.5 last:border-b-0"
                >
                  <div className="mt-1.5">
                    <PriorityDot priority={item.priority === "critical" ? "critical" : item.priority === "warning" ? "warning" : "info"} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-900 line-clamp-1">{item.description}</p>
                    <p className="text-xs text-gray-500">
                      {item.client_name}
                      {item.overdue_days != null && item.overdue_days > 0
                        ? ` — Overdue by ${item.overdue_days} day${item.overdue_days !== 1 ? "s" : ""}`
                        : item.due_date
                        ? (() => {
                            const diff = Math.ceil(
                              (new Date(item.due_date).getTime() - Date.now()) /
                                86400000,
                            );
                            if (diff === 0) return " — Due today";
                            if (diff === 1) return " — Due tomorrow";
                            return ` — Due in ${diff} days`;
                          })()
                        : ""}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        {/* Team members or Recent clients */}
        {data.team_members ? (
          <SectionCard
            title="Team"
            action={{ label: "Manage", href: "/dashboard/settings/organization" }}
          >
            {data.team_members.slice(0, 5).map((m) => (
              <MemberRow
                key={m.user_id}
                name={m.name}
                email={m.email}
                role={m.role}
                stats={{ clients: 0, queries: m.queries_used }}
                lastActive={
                  m.last_active
                    ? new Date(m.last_active).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    : undefined
                }
              />
            ))}
          </SectionCard>
        ) : (
          <SectionCard
            title="Recent clients"
            action={{ label: "View all", href: "/dashboard/clients" }}
          >
            {data.recent_clients.slice(0, 5).map((c) => (
              <Link
                key={c.id}
                href={`/dashboard/clients/${c.id}`}
                className="flex items-center gap-3 border-b border-gray-100 py-2.5 last:border-b-0 hover:bg-gray-50 -mx-1 px-1 rounded"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-blue-50 text-[11px] font-medium text-blue-700">
                  {c.name
                    .split(/\s+/)
                    .map((w) => w[0])
                    .join("")
                    .slice(0, 2)
                    .toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-gray-900">{c.name}</p>
                  <p className="text-xs text-gray-500">
                    {c.document_count} document{c.document_count !== 1 ? "s" : ""}
                    {" · "}
                    {c.action_item_count} action item{c.action_item_count !== 1 ? "s" : ""}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-gray-400">
                  {new Date(c.last_activity).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })}
                </span>
              </Link>
            ))}
            <Link
              href="/dashboard/clients/new"
              className="mt-3 flex w-full items-center justify-center rounded-lg border border-dashed border-gray-200 py-2 text-sm text-gray-500 hover:border-gray-400 hover:text-gray-700"
            >
              + Add new client
            </Link>
          </SectionCard>
        )}
      </div>
    </div>
  );
}
