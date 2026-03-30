"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import type { DashboardSummary, MemberAssignments } from "@/lib/api";
import { createClientAssignmentsApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import StatCard from "@/components/ui/StatCard";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import SectionCard from "@/components/ui/SectionCard";
import MemberRow from "@/components/ui/MemberRow";

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

export default function AdminDashboard({ data, initials, timeRange, onTimeRangeChange }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [assignmentMap, setAssignmentMap] = useState<Record<string, MemberAssignments>>({});

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

  const { stats } = data;
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

      {/* Row 1: Stat cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Active clients"
          value={stats.clients.count}
          context={stats.clients.limit != null ? `of ${stats.clients.limit}` : undefined}
          contextType="muted"
          accentColor="border-l-blue-500"
        />
        <StatCard
          label="Action items"
          value={stats.action_items.pending}
          context={stats.action_items.overdue > 0 ? `${stats.action_items.overdue} overdue` : "All on track"}
          contextType={stats.action_items.overdue > 0 ? "warning" : "success"}
          accentColor="border-l-amber-500"
        />
        <StatCard
          label="Documents"
          value={stats.documents.count}
          context={stats.documents.limit != null ? `of ${stats.documents.limit}` : undefined}
          contextType="muted"
          accentColor="border-l-teal-500"
        />
        <StatCard
          label="AI queries"
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
          <AreaChartCard title="Activity" data={chartData} timeRange={timeRange} onTimeRangeChange={onTimeRangeChange} />
        </div>
        <div className="lg:col-span-2">
          <DonutChartCard title="Query distribution" data={donutData} centerValue={totalQueries} centerLabel="queries" titleExtra={<HelpTooltip content="Shows how your AI queries are routed: factual lookups, multi-document synthesis, or strategic advisory analysis." />} />
        </div>
      </div>

      {/* Row 3: Content cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AttentionCard data={data} />
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
          <RecentClientsCard data={data} />
        )}
      </div>

      {/* Row 4: Utility cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {data.team_members ? <RecentClientsCard data={data} /> : <QuickActionsCard data={data} />}
        <UsageCard data={data} />
      </div>
    </div>
  );
}
