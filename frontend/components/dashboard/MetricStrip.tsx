"use client";

import Link from "next/link";

/* ── Mini progress ring ──────────────────────────────────────────────────── */

function MiniRing({ pct }: { pct: number }) {
  const r = 16;
  const stroke = 4;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct > 80 ? "#ef4444" : pct >= 60 ? "#f59e0b" : "#3b82f6";

  return (
    <svg width={40} height={40} viewBox="0 0 40 40" className="shrink-0">
      <circle cx={20} cy={20} r={r} fill="none" stroke="#f3f4f6" strokeWidth={stroke} />
      <circle
        cx={20}
        cy={20}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform="rotate(-90 20 20)"
      />
    </svg>
  );
}

/* ── Inline SVG icons ────────────────────────────────────────────────────── */

function TrendingUpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

function UsersIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 00-3-3.87" />
      <path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  );
}

function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

/* ── Metric card wrapper ──────────────────────────────────────────────────── */

function MetricCard({
  href,
  label,
  value,
  subtitle,
  indicator,
}: {
  href: string;
  label: string;
  value: string;
  subtitle: string;
  indicator: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3.5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md"
    >
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">{label}</p>
        <p className="mt-0.5 text-[22px] font-semibold leading-tight text-gray-900">{value}</p>
        <p className="mt-0.5 text-[11px] text-gray-400">{subtitle}</p>
      </div>
      <div className="shrink-0">{indicator}</div>
    </Link>
  );
}

/* ── Props ────────────────────────────────────────────────────────────────── */

interface MetricStripProps {
  savings: number | null;
  aiQueries: { used: number; limit: number };
  activeClients: { count: number; limit: number | null };
  completedThisWeek: number;
  tier: string;
}

/* ── Main component ───────────────────────────────────────────────────────── */

export default function MetricStrip({
  savings,
  aiQueries,
  activeClients,
  completedThisWeek,
  tier,
}: MetricStripProps) {
  const savingsStr =
    savings != null
      ? new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0,
        }).format(savings)
      : "$0";

  const pct = aiQueries.limit > 0 ? Math.min((aiQueries.used / aiQueries.limit) * 100, 100) : 0;

  const clientSubtitle =
    activeClients.limit != null && (tier === "free" || tier === "starter")
      ? `of ${activeClients.limit}`
      : "managed";

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard
        href="/dashboard/strategy-dashboard"
        label="Client Savings"
        value={savingsStr}
        subtitle="this year"
        indicator={
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-green-50">
            <TrendingUpIcon className="h-5 w-5 text-green-500" />
          </div>
        }
      />

      <MetricCard
        href="/dashboard/settings/subscriptions"
        label="AI Queries"
        value={`${aiQueries.used} / ${aiQueries.limit}`}
        subtitle="this period"
        indicator={<MiniRing pct={pct} />}
      />

      <MetricCard
        href="/dashboard/clients"
        label="Active Clients"
        value={String(activeClients.count)}
        subtitle={clientSubtitle}
        indicator={
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-50">
            <UsersIcon className="h-5 w-5 text-blue-500" />
          </div>
        }
      />

      <MetricCard
        href="/dashboard/action-items"
        label="Completed"
        value={String(completedThisWeek)}
        subtitle="this week"
        indicator={
          <div className={`flex h-9 w-9 items-center justify-center rounded-full ${completedThisWeek > 0 ? "bg-green-50" : "bg-gray-50"}`}>
            <CheckCircleIcon className={`h-5 w-5 ${completedThisWeek > 0 ? "text-green-500" : "text-gray-400"}`} />
          </div>
        }
      />
    </div>
  );
}
