"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import type { DashboardSummary, PriorityFeedItem, RevenueImpact, StrategyOverview } from "@/lib/api";
import { createDashboardApi, createStrategyDashboardApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import CoverageRing from "@/components/dashboard/CoverageRing";
import RevenueImpactCard from "@/components/dashboard/RevenueImpactCard";
import ClientCommandCard from "@/components/dashboard/ClientCommandCard";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import HelpTooltip from "@/components/ui/HelpTooltip";

import {
  type TimeRange,
  DIST_COLORS,
  AttentionCard,
  UsageCard,
} from "./shared";

interface Props {
  data: DashboardSummary;
  initials: string;
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

export default function MemberDashboard({ data, initials, timeRange, onTimeRangeChange }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [strategyOverview, setStrategyOverview] = useState<StrategyOverview | null>(null);
  const [feedItems, setFeedItems] = useState<PriorityFeedItem[] | null>(null);
  const [revenueImpact, setRevenueImpact] = useState<RevenueImpact | null>(null);
  const { stats } = data;

  useEffect(() => {
    const api = createStrategyDashboardApi(getToken, activeOrg?.id);
    api.fetchOverview(new Date().getFullYear()).then(setStrategyOverview).catch(() => {});
  }, [getToken, activeOrg]);

  useEffect(() => {
    const api = createDashboardApi(getToken, activeOrg?.id);
    api.priorityFeed().then(setFeedItems).catch(() => {});
    api.revenueImpact(new Date().getFullYear()).then(setRevenueImpact).catch(() => {});
  }, [getToken, activeOrg]);

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

      {/* Row 1: Client command bar */}
      <div className="mb-6">
        <ClientCommandCard clients={data.recent_clients} />
      </div>

      {/* Row 2: Impact metrics */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_0.8fr]">
        <RevenueImpactCard data={revenueImpact} />
        <CoverageRing
          reviewed={strategyOverview?.clients_reviewed ?? null}
          total={strategyOverview?.total_clients ?? null}
          href="/dashboard/strategy-dashboard"
        />
      </div>

      {/* Row 3: Activity trends */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <AreaChartCard title="My activity" data={chartData} timeRange={timeRange} onTimeRangeChange={onTimeRangeChange} />
        </div>
        <div className="lg:col-span-2">
          <DonutChartCard title="Query distribution" data={donutData} centerValue={totalQueries} centerLabel="queries" titleExtra={<HelpTooltip content="Shows how your AI queries are routed: factual lookups, multi-document synthesis, or strategic advisory analysis." />} />
        </div>
      </div>

      {/* Row 4: Attention + Usage */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AttentionCard data={data} feedItems={feedItems} />
        <UsageCard data={data} showSeats={false} showUpgrade={false} />
      </div>
    </div>
  );
}
