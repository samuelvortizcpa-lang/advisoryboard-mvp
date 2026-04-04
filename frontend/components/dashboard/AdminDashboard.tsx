"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import type { DashboardSummary, MemberAssignments, PriorityFeedItem, RevenueImpact, StrategyOverview } from "@/lib/api";
import { createClientAssignmentsApi, createDashboardApi, createStrategyDashboardApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import CoverageRing from "@/components/dashboard/CoverageRing";
import RevenueImpactCard from "@/components/dashboard/RevenueImpactCard";
import ClientCommandCard from "@/components/dashboard/ClientCommandCard";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import SectionCard from "@/components/ui/SectionCard";
import MemberRow from "@/components/ui/MemberRow";

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

export default function AdminDashboard({ data, initials, timeRange, onTimeRangeChange }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [assignmentMap, setAssignmentMap] = useState<Record<string, MemberAssignments>>({});
  const [strategyOverview, setStrategyOverview] = useState<StrategyOverview | null>(null);
  const [feedItems, setFeedItems] = useState<PriorityFeedItem[] | null>(null);
  const [revenueImpact, setRevenueImpact] = useState<RevenueImpact | null>(null);

  const loadAssignments = useCallback(async () => {
    if (!activeOrg || activeOrg.org_type === "personal") return;
    try {
      const api = createClientAssignmentsApi(getToken, activeOrg.id);
      const result = await api.listOrgAssignments(activeOrg.id);
      const map: Record<string, MemberAssignments> = {};
      for (const m of result) {
        map[m.user_id] = m;
      }
      setAssignmentMap(map);
    } catch {
      // non-fatal
    }
  }, [getToken, activeOrg]);

  useEffect(() => {
    if (data.team_members) {
      loadAssignments();
    }
  }, [data.team_members, loadAssignments]);

  useEffect(() => {
    const api = createStrategyDashboardApi(getToken, activeOrg?.id);
    api.fetchOverview(new Date().getFullYear()).then(setStrategyOverview).catch(() => {});
  }, [getToken, activeOrg]);

  useEffect(() => {
    const api = createDashboardApi(getToken, activeOrg?.id);
    api.priorityFeed().then(setFeedItems).catch(() => {});
    api.revenueImpact(new Date().getFullYear()).then(setRevenueImpact).catch(() => {});
  }, [getToken, activeOrg]);

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
        <h1 className="text-2xl font-semibold text-gray-900">Overview</h1>
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
          <AreaChartCard title="Activity" data={chartData} timeRange={timeRange} onTimeRangeChange={onTimeRangeChange} />
        </div>
        <div className="lg:col-span-2">
          <DonutChartCard title="Query distribution" data={donutData} centerValue={totalQueries} centerLabel="queries" titleExtra={<HelpTooltip content="Shows how your AI queries are routed: factual lookups, multi-document synthesis, or strategic advisory analysis." />} />
        </div>
      </div>

      {/* Row 4: Attention + Team/Plan */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AttentionCard data={data} feedItems={feedItems} />
        {data.team_members ? (
          <SectionCard title="Team" action={{ label: "Manage", href: "/dashboard/settings/organization" }}>
            {data.team_members.slice(0, 5).map((m) => {
              const memberAssign = assignmentMap[m.user_id];
              const clientCount = memberAssign?.assigned_clients.length ?? 0;
              const clientNames = memberAssign?.assigned_clients.map((c) => c.client_name) ?? [];
              return (
                <MemberRow
                  key={m.user_id}
                  name={m.name}
                  email={m.email}
                  role={m.role}
                  stats={{ clients: clientCount, queries: m.queries_used }}
                  clientNames={clientNames}
                  lastActive={
                    m.last_active
                      ? new Date(m.last_active).toLocaleDateString("en-US", { month: "short", day: "numeric" })
                      : undefined
                  }
                />
              );
            })}
          </SectionCard>
        ) : (
          <UsageCard data={data} />
        )}
      </div>

      {/* Row 5: Usage (for firm tier that shows team above) */}
      {data.team_members && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <UsageCard data={data} />
        </div>
      )}
    </div>
  );
}
