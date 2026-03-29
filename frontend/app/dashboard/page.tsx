"use client";

import { useAuth, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

import { createDashboardApi, type DashboardSummary } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import { type TimeRange, RANGE_DAYS, DashboardSkeleton } from "@/components/dashboard/shared";
import AdminDashboard from "@/components/dashboard/AdminDashboard";
import MemberDashboard from "@/components/dashboard/MemberDashboard";

export default function DashboardPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const { activeOrg, isAdmin, isPersonalOrg, isLoading: orgLoading } = useOrg();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(
    async (range: TimeRange) => {
      try {
        const token = await getToken();
        if (!token) return false; // auth not ready yet
        const api = createDashboardApi(getToken, activeOrg?.id);
        const result = await api.summary(RANGE_DAYS[range]);
        setData(result);
        return true;
      } catch (err) {
        console.error("Dashboard fetch failed:", err);
        return false;
      }
    },
    [getToken, activeOrg?.id],
  );

  useEffect(() => {
    if (!isLoaded || !isSignedIn || orgLoading) return;

    let cancelled = false;
    (async () => {
      const ok = await load(timeRange);
      // If the fetch failed (e.g. token not ready yet), retry once after a short delay
      if (!ok && !cancelled) {
        retryTimer.current = setTimeout(() => {
          if (!cancelled) load(timeRange);
        }, 1000);
      }
    })();

    return () => {
      cancelled = true;
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, [load, timeRange, isLoaded, isSignedIn, orgLoading]);

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
