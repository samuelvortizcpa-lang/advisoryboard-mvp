"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

import type { DashboardSummary, IntegrationConnection, RevenueImpact } from "@/lib/api";
import { createDashboardApi, createIntegrationsApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import ClientCommandCard from "@/components/dashboard/ClientCommandCard";
import TaskBoard from "@/components/dashboard/TaskBoard";
import MetricStrip from "@/components/dashboard/MetricStrip";
import type { ConnectionStatus } from "@/components/dashboard/MetricStrip";
import AreaChartCard from "@/components/ui/AreaChartCard";
import DonutChartCard from "@/components/ui/DonutChartCard";
import HelpTooltip from "@/components/ui/HelpTooltip";
import ContextualTooltip from "@/components/ui/ContextualTooltip";

import {
  type TimeRange,
  DIST_COLORS,
} from "./shared";

function deriveConnections(conns: IntegrationConnection[]): ConnectionStatus {
  return {
    email: conns.some((c) => (c.provider === "google" || c.provider === "microsoft") && c.is_active),
    calendar: conns.some((c) => c.provider === "google" && c.is_active && c.scopes?.includes("calendar")),
    zoom: conns.some((c) => c.provider === "zoom" && c.is_active),
  };
}

interface Props {
  data: DashboardSummary;
  initials?: string;
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

export default function AdminDashboard({ data, timeRange, onTimeRangeChange }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [revenueImpact, setRevenueImpact] = useState<RevenueImpact | null>(null);
  const [connections, setConnections] = useState<ConnectionStatus | null>(null);
  const [dismissedTooltips, setDismissedTooltips] = useState<string[]>(data.dismissed_tooltips ?? []);
  const clientCardRef = useRef<HTMLDivElement>(null);

  const handleTooltipDismiss = useCallback((id: string) => {
    setDismissedTooltips((prev) => prev.includes(id) ? prev : [...prev, id]);
  }, []);

  useEffect(() => {
    const dashApi = createDashboardApi(getToken, activeOrg?.id);
    dashApi.revenueImpact(new Date().getFullYear()).then(setRevenueImpact).catch(() => {});

    const intApi = createIntegrationsApi(getToken, activeOrg?.id);
    intApi.listConnections().then((conns) => setConnections(deriveConnections(conns))).catch(() => {});
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
      </div>

      {/* Row 1: Client Hub + Task Board */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <div className="lg:col-span-5" ref={clientCardRef}>
          <ClientCommandCard clients={data.recent_clients} />
        </div>
        <div className="lg:col-span-7">
          <TaskBoard data={data} />
        </div>
      </div>

      {/* Row 2: Metric Strip */}
      <MetricStrip
        savings={revenueImpact?.total_estimated_savings ?? null}
        aiQueries={data.stats.ai_queries}
        activeClients={data.stats.clients}
        connections={connections}
        tier={data.plan.tier}
      />

      {/* Row 3: Activity trends */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[3fr_2fr]">
        <AreaChartCard title="Activity" data={chartData} timeRange={timeRange} onTimeRangeChange={onTimeRangeChange} />
        <DonutChartCard title="Query distribution" data={donutData} centerValue={totalQueries} centerLabel="queries" titleExtra={<HelpTooltip content="Shows how your AI queries are routed: factual lookups, multi-document synthesis, or strategic advisory analysis." />} />
      </div>
      {/* Contextual tooltip for client search */}
      <ContextualTooltip
        tooltipId="dashboard_command_bar"
        targetRef={clientCardRef}
        title="Quick client search"
        description="Start typing to find any client instantly. Press Enter to jump to the first match."
        position="bottom"
        dismissedTooltips={dismissedTooltips}
        onDismiss={handleTooltipDismiss}
      />
    </div>
  );
}
