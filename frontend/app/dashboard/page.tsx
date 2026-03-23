"use client";

import Link from "next/link";
import { useAuth, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { createDashboardApi, type DashboardSummary } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import StatCard from "@/components/ui/StatCard";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";

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
    </div>
  );
}
