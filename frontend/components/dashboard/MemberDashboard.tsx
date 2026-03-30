"use client";

import Link from "next/link";

import type { DashboardSummary } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import HelpTooltip from "@/components/ui/HelpTooltip";

import {
  type TimeRange,
  DIST_COLORS,
  AttentionCard,
  RecentClientsCard,
  QuickActionsCard,
  UsageCard,
} from "./shared";

interface Props {
  data: DashboardSummary;
  initials: string;
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

export default function MemberDashboard({ data, initials, timeRange, onTimeRangeChange }: Props) {
  const { stats } = data;

  // Empty state: org member with no assigned clients
  const isOrgMember = data.team_members != null;
  if (isOrgMember && stats.clients.count === 0) {
    return (
      <div>
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-gray-900">My Overview</h1>
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-[11px] font-medium text-blue-700">
            {initials}
          </div>
        </div>
        <div className="flex flex-col items-center justify-center rounded-xl border border-gray-200 bg-white py-20 px-6 text-center shadow-sm">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gray-100 mb-4">
            <svg className="h-7 w-7 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <h2 className="text-base font-semibold text-gray-900">No clients assigned yet</h2>
          <p className="mt-1.5 max-w-sm text-sm text-gray-500">
            Your admin hasn&apos;t assigned any clients to you yet. Once they do, your
            clients and their data will appear here.
          </p>
        </div>
      </div>
    );
  }
  const queryPct =
    stats.ai_queries.limit > 0
      ? (stats.ai_queries.used / stats.ai_queries.limit) * 100
      : 0;

  const chartData = data.activity_chart.map((p) => ({ date: p.date, value: p.queries }));

  const donutData = data.query_distribution.map((d) => ({
    name: d.type,
    value: d.count,
    color: DIST_COLORS[d.type] ?? DIST_COLORS.Other,
  }));

  const totalQueries = data.query_distribution.reduce((s, d) => s + d.count, 0);

  return (
    <div>
      {/* Top bar */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">My Overview</h1>
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard/clients/new"
            className="rounded-lg bg-[#c9944a] px-4 py-2 text-sm font-medium text-white hover:bg-[#b8843e]"
          >
            + New client
          </Link>
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-[11px] font-medium text-blue-700">
            {initials}
          </div>
        </div>
      </div>

      {/* Row 1: Stat cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="My clients"
          value={stats.clients.count}
          context={stats.clients.limit != null ? `of ${stats.clients.limit}` : undefined}
          contextType="muted"
          accentColor="border-l-blue-500"
        />
        <StatCard
          label="My action items"
          value={stats.action_items.pending}
          context={stats.action_items.overdue > 0 ? `${stats.action_items.overdue} overdue` : "All on track"}
          contextType={stats.action_items.overdue > 0 ? "warning" : "success"}
          accentColor="border-l-amber-500"
        />
        <StatCard
          label="My documents"
          value={stats.documents.count}
          context={stats.documents.limit != null ? `of ${stats.documents.limit}` : undefined}
          contextType="muted"
          accentColor="border-l-teal-500"
        />
        <StatCard
          label="My AI queries"
          value={stats.ai_queries.used}
          context={`of ${stats.ai_queries.limit}`}
          contextType={queryPct > 80 ? "warning" : "muted"}
          accentColor="border-l-purple-500"
          labelExtra={<HelpTooltip content="Total AI questions asked across all clients this billing period." />}
        />
      </div>

      {/* Row 2: Charts */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <AreaChartCard title="My activity" data={chartData} timeRange={timeRange} onTimeRangeChange={onTimeRangeChange} />
        </div>
        <div className="lg:col-span-2">
          <DonutChartCard title="Query distribution" data={donutData} centerValue={totalQueries} centerLabel="queries" titleExtra={<HelpTooltip content="Shows how your AI queries are routed: factual lookups, multi-document synthesis, or strategic advisory analysis." />} />
        </div>
      </div>

      {/* Row 3: Content cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AttentionCard data={data} />
        <RecentClientsCard data={data} />
      </div>

      {/* Row 4: Utility cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <QuickActionsCard data={data} />
        <UsageCard data={data} showSeats={false} showUpgrade={false} />
      </div>
    </div>
  );
}
