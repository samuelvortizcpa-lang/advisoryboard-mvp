"use client";

import Link from "next/link";
import { useAuth, useUser } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import AlertsList from "@/components/alerts/AlertsList";
import UsageStats from "@/components/dashboard/UsageStats";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DashboardStats {
  clients: number;
  documents: number;
  interactions: number;
}

export default function DashboardPage() {
  const { getToken, userId } = useAuth();
  const { user } = useUser();
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const token = await getToken();
      if (!token || cancelled) return;
      try {
        const res = await fetch(`${API_BASE}/api/dashboard/stats`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error("stats fetch failed");
        const data: DashboardStats = await res.json();
        if (!cancelled) setStats(data);
      } catch {
        if (!cancelled) setStats({ clients: 0, documents: 0, interactions: 0 });
      }
    }

    load();
    return () => { cancelled = true; };
  }, [getToken]);

  const displayName =
    [user?.firstName, user?.lastName].filter(Boolean).join(" ") || "there";
  const email = user?.emailAddresses[0]?.emailAddress ?? "";

  if (!stats) {
    return (
      <div className="px-8 py-8">
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm animate-pulse">
          <div className="h-3 w-20 rounded bg-gray-200" />
          <div className="mt-3 h-6 w-64 rounded bg-gray-200" />
          <div className="mt-2 h-4 w-40 rounded bg-gray-100" />
          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-lg border border-gray-100 bg-gray-50 px-5 py-4">
                <div className="h-7 w-10 rounded bg-gray-200" />
                <div className="mt-2 h-4 w-20 rounded bg-gray-100" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-8">
      {/* Welcome card */}
      <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Dashboard
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">
          Welcome back, {displayName}
        </h1>
        {email && (
          <p className="mt-1 text-sm text-gray-500">{email}</p>
        )}

        <p className="mt-5 leading-relaxed text-gray-600 text-sm">
          Manage your CPA client relationships, log interactions, and organise
          documents — all in one place.
        </p>

        {/* Stats */}
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {/* Clients */}
          <Link
            href="/dashboard/clients"
            className="group rounded-lg border border-gray-100 bg-gray-50 px-5 py-4 transition-colors hover:border-blue-200 hover:bg-blue-50"
          >
            <p className="text-2xl font-bold text-gray-900 transition-colors group-hover:text-blue-700">
              {stats.clients}
            </p>
            <p className="mt-0.5 text-sm text-gray-500 transition-colors group-hover:text-blue-600">
              Clients →
            </p>
          </Link>

          {/* Interactions (action items) */}
          <Link
            href="/dashboard/actions"
            className="group rounded-lg border border-gray-100 bg-gray-50 px-5 py-4 transition-colors hover:border-blue-200 hover:bg-blue-50"
          >
            <p className="text-2xl font-bold text-gray-900 transition-colors group-hover:text-blue-700">
              {stats.interactions}
            </p>
            <p className="mt-0.5 text-sm text-gray-500 transition-colors group-hover:text-blue-600">
              Action Items →
            </p>
          </Link>

          {/* Documents */}
          <Link
            href="/dashboard/clients"
            className="group rounded-lg border border-gray-100 bg-gray-50 px-5 py-4 transition-colors hover:border-blue-200 hover:bg-blue-50"
          >
            <p className="text-2xl font-bold text-gray-900 transition-colors group-hover:text-blue-700">
              {stats.documents}
            </p>
            <p className="mt-0.5 text-sm text-gray-500 transition-colors group-hover:text-blue-600">
              Documents →
            </p>
          </Link>
        </div>
      </div>

      {/* Smart Alerts */}
      <div className="mt-6">
        <AlertsList />
      </div>

      {/* AI Usage */}
      <div className="mt-6">
        <UsageStats />
      </div>

      {/* Quick actions */}
      <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          Quick Actions
        </h2>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link
            href="/dashboard/clients/new"
            className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
          >
            + Add Client
          </Link>
          <Link
            href="/dashboard/clients"
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            View All Clients
          </Link>
        </div>
      </div>

      {/* Account details */}
      <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          Account
        </h2>
        <dl className="mt-4 space-y-3">
          <Row label="Name" value={displayName} />
          <Row label="Email" value={email || "—"} />
          <Row label="User ID" value={userId || "—"} mono />
        </dl>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-4 text-sm">
      <dt className="w-20 shrink-0 font-medium text-gray-500">{label}</dt>
      <dd className={`text-gray-900 ${mono ? "font-mono text-xs break-all" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
