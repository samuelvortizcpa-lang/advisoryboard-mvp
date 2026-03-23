"use client";

import { useAuth, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { createDashboardApi, type DashboardSummary } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import { type TimeRange, RANGE_DAYS, DashboardSkeleton } from "@/components/dashboard/shared";
import AdminDashboard from "@/components/dashboard/AdminDashboard";
import MemberDashboard from "@/components/dashboard/MemberDashboard";

export default function DashboardPage() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const { activeOrg, isAdmin, isPersonalOrg } = useOrg();
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

  const initials =
    ((user?.firstName?.[0] ?? "") + (user?.lastName?.[0] ?? "")).toUpperCase() ||
    "U";

  if (!data) {
    return <DashboardSkeleton />;
  }

  // Solo practitioners (personal org) and org admins see admin dashboard;
  // org members (non-admin) see member dashboard
  const showAdminView = isPersonalOrg || isAdmin;
  const Dashboard = showAdminView ? AdminDashboard : MemberDashboard;

  return (
    <Dashboard
      data={data}
      initials={initials}
      timeRange={timeRange}
      onTimeRangeChange={setTimeRange}
    />
  );
}
