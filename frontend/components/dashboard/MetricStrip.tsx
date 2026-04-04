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

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function LinkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
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
  children,
}: {
  href: string;
  label: string;
  value?: string;
  subtitle?: string;
  indicator: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3.5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md"
    >
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">{label}</p>
        {value != null && (
          <p className="mt-0.5 text-[22px] font-semibold leading-tight text-gray-900">{value}</p>
        )}
        {subtitle && (
          <p className="mt-0.5 text-[11px] text-gray-400">{subtitle}</p>
        )}
        {children}
      </div>
      <div className="shrink-0 ml-3">{indicator}</div>
    </Link>
  );
}

/* ── Props ────────────────────────────────────────────────────────────────── */

export interface ConnectionStatus {
  email: boolean;
  calendar: boolean;
  zoom: boolean;
}

interface MetricStripProps {
  savings: number | null;
  aiQueries: { used: number; limit: number };
  activeClients: { count: number; limit: number | null };
  connections: ConnectionStatus | null;
  tier: string;
}

/* ── Main component ───────────────────────────────────────────────────────── */

export default function MetricStrip({
  savings,
  aiQueries,
  activeClients,
  connections,
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
      : "across all engagements";

  // Connection status
  const conn = connections ?? { email: false, calendar: false, zoom: false };
  const allConnected = conn.email && conn.calendar && conn.zoom;

  const connCount = [conn.email, conn.calendar, conn.zoom].filter(Boolean).length;

  const connIndicator = allConnected ? (
    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-green-50">
      <CheckIcon className="h-5 w-5 text-green-500" />
    </div>
  ) : (
    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gray-50">
      <LinkIcon className="h-5 w-5 text-gray-400" />
    </div>
  );

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard
        href="/dashboard/strategy-dashboard"
        label="Client Savings"
        value={savingsStr}
        subtitle="2026 year to date"
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
        subtitle="current billing period"
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
        href="/dashboard/settings/integrations"
        label="Connections"
        value={`${connCount} / 3`}
        subtitle="integrations active"
        indicator={connIndicator}
      >
        <div className="mt-1 flex items-center gap-1">
          <span className={`inline-block h-2 w-2 rounded-full ${conn.email ? "bg-green-500" : "bg-gray-300"}`} />
          <span className={`inline-block h-2 w-2 rounded-full ${conn.calendar ? "bg-green-500" : "bg-gray-300"}`} />
          <span className={`inline-block h-2 w-2 rounded-full ${conn.zoom ? "bg-green-500" : "bg-gray-300"}`} />
        </div>
      </MetricCard>
    </div>
  );
}
