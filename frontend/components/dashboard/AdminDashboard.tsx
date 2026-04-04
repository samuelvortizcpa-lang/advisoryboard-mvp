"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import type { DashboardSummary, DeadlineItem, RevenueImpact } from "@/lib/api";
import { createDashboardApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import ClientCommandCard from "@/components/dashboard/ClientCommandCard";
import TaskBoard from "@/components/dashboard/TaskBoard";
import MetricStrip from "@/components/dashboard/MetricStrip";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import HelpTooltip from "@/components/ui/HelpTooltip";

import {
  type TimeRange,
  DIST_COLORS,
} from "./shared";

interface Props {
  data: DashboardSummary;
  initials: string;
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

export default function AdminDashboard({ data, initials, timeRange, onTimeRangeChange }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [revenueImpact, setRevenueImpact] = useState<RevenueImpact | null>(null);
  const [deadlines, setDeadlines] = useState<DeadlineItem[] | null>(null);

  useEffect(() => {
    const api = createDashboardApi(getToken, activeOrg?.id);
    api.revenueImpact(new Date().getFullYear()).then(setRevenueImpact).catch(() => {});
    api.upcomingDeadlines().then(setDeadlines).catch(() => {});
  }, [getToken, activeOrg]);

  const chartData = data.activity_chart.map((p) => ({ date: p.date, value: p.queries }));

  const donutData = data.query_distribution.map((d) => ({
    name: d.type,
    value: d.count,
    color: DIST_COLORS[d.type] ?? DIST_COLORS.Other,
  }));

  const totalQueries = data.query_distribution.reduce((s, d) => s + d.count, 0);

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex items-center justify-end gap-3">
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

      {/* Row 1: Client Hub + Task Board */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <ClientCommandCard clients={data.recent_clients} />
        <TaskBoard items={deadlines} />
      </div>

      {/* Row 2: Metric Strip */}
      <MetricStrip
        savings={revenueImpact?.total_estimated_savings ?? null}
        aiQueries={data.stats.ai_queries}
        activeClients={data.stats.clients}
        completedThisWeek={data.stats.action_items.completed_this_week}
        tier={data.plan.tier}
      />

      {/* Row 3: Activity trends */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[3fr_2fr]">
        <AreaChartCard title="Activity" data={chartData} timeRange={timeRange} onTimeRangeChange={onTimeRangeChange} />
        <DonutChartCard title="Query distribution" data={donutData} centerValue={totalQueries} centerLabel="queries" titleExtra={<HelpTooltip content="Shows how your AI queries are routed: factual lookups, multi-document synthesis, or strategic advisory analysis." />} />
      </div>
    </div>
  );
}
