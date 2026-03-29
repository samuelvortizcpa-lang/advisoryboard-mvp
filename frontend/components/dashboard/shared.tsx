"use client";

import Link from "next/link";

import type { DashboardSummary } from "@/lib/api";
import SectionCard from "@/components/ui/SectionCard";
import PriorityDot from "@/components/ui/PriorityDot";
import ThinProgress from "@/components/ui/ThinProgress";

// ─── Types ───────────────────────────────────────────────────────────────────

export type TimeRange = "7d" | "30d" | "90d";

export const RANGE_DAYS: Record<TimeRange, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
};

export const DIST_COLORS: Record<string, string> = {
  "Quick Lookup": "#3B82F6",
  "Deep Analysis": "#8B5CF6",
  Brief: "#14B8A6",
  "Action Items": "#F59E0B",
  Other: "#D1D5DB",
};

export const TIER_BADGE_COLORS: Record<string, string> = {
  firm: "bg-indigo-100 text-indigo-700",
  professional: "bg-purple-100 text-purple-700",
  starter: "bg-blue-100 text-blue-700",
  free: "bg-gray-100 text-gray-700",
};

// ─── Loading skeleton ────────────────────────────────────────────────────────

export function DashboardSkeleton() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Overview</h1>
        <div className="flex items-center gap-3">
          <div className="h-9 w-28 animate-pulse rounded-lg bg-gray-200" />
          <div className="h-7 w-7 animate-pulse rounded-full bg-gray-200" />
        </div>
      </div>
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="animate-pulse rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
            <div className="h-3 w-16 rounded bg-gray-200" />
            <div className="mt-2 h-8 w-12 rounded bg-gray-200" />
            <div className="mt-2 h-3 w-20 rounded bg-gray-100" />
          </div>
        ))}
      </div>
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 lg:col-span-3">
          <div className="h-4 w-24 rounded bg-gray-200" />
          <div className="mt-4 h-[240px] rounded bg-gray-50" />
        </div>
        <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 lg:col-span-2">
          <div className="h-4 w-32 rounded bg-gray-200" />
          <div className="mt-4 h-[240px] rounded bg-gray-50" />
        </div>
      </div>
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {[1, 2].map((i) => (
          <div key={i} className="animate-pulse rounded-xl border border-gray-200 bg-white p-5">
            <div className="h-4 w-28 rounded bg-gray-200" />
            <div className="mt-4 space-y-3">
              {[1, 2, 3].map((j) => (
                <div key={j} className="h-10 rounded bg-gray-50" />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {[1, 2].map((i) => (
          <div key={i} className="animate-pulse rounded-xl border border-gray-200 bg-white p-5">
            <div className="h-4 w-20 rounded bg-gray-200" />
            <div className="mt-4 space-y-3">
              {[1, 2].map((j) => (
                <div key={j} className="h-6 rounded bg-gray-50" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Shared sub-components ───────────────────────────────────────────────────

export function AttentionCard({ data }: { data: DashboardSummary }) {
  return (
    <SectionCard
      title="Needs attention"
      action={{ label: "View all", href: "/dashboard/actions" }}
    >
      {data.attention_items.length === 0 ? (
        <div className="flex items-center gap-2 py-2">
          <svg className="h-4 w-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm text-gray-500">All caught up</span>
        </div>
      ) : (
        <div>
          {data.attention_items.slice(0, 5).map((item) => (
            <div
              key={item.id}
              className="flex items-start gap-2.5 border-b border-gray-100 py-2.5 last:border-b-0"
            >
              <div className="mt-1.5">
                <PriorityDot priority={item.priority === "critical" ? "critical" : item.priority === "warning" ? "warning" : "info"} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-gray-900 line-clamp-1">{item.description}</p>
                <p className="text-xs text-gray-500">
                  {item.client_name}
                  {item.overdue_days != null && item.overdue_days > 0
                    ? ` — Overdue by ${item.overdue_days} day${item.overdue_days !== 1 ? "s" : ""}`
                    : item.due_date
                    ? (() => {
                        const diff = Math.ceil(
                          (new Date(item.due_date).getTime() - Date.now()) / 86400000,
                        );
                        if (diff === 0) return " — Due today";
                        if (diff === 1) return " — Due tomorrow";
                        return ` — Due in ${diff} days`;
                      })()
                    : ""}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

export function RecentClientsCard({ data }: { data: DashboardSummary }) {
  return (
    <SectionCard
      title="Recent clients"
      action={{ label: "View all", href: "/dashboard/clients" }}
    >
      {data.recent_clients.slice(0, 5).map((c) => (
        <Link
          key={c.id}
          href={`/dashboard/clients/${c.id}`}
          className="flex items-center gap-3 border-b border-gray-100 py-2.5 last:border-b-0 hover:bg-gray-50 -mx-1 px-1 rounded"
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-blue-50 text-[11px] font-medium text-blue-700">
            {c.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-gray-900">{c.name}</p>
            <p className="text-xs text-gray-500">
              {c.document_count} document{c.document_count !== 1 ? "s" : ""}
              {" · "}
              {c.action_item_count} action item{c.action_item_count !== 1 ? "s" : ""}
            </p>
          </div>
          <span className="shrink-0 text-xs text-gray-400">
            {new Date(c.last_activity).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
          </span>
        </Link>
      ))}
    </SectionCard>
  );
}

export function QuickActionsCard({ data }: { data: DashboardSummary }) {
  const firstClient = data.recent_clients[0];
  const clientLink = firstClient
    ? `/dashboard/clients/${firstClient.id}`
    : "/dashboard/clients/new";

  return (
    <SectionCard title="Quick actions">
      <div className="grid grid-cols-2 gap-2">
        <Link href={clientLink} className="rounded-lg border border-gray-200 px-3 py-2.5 text-center text-sm text-gray-600 hover:border-gray-300 hover:bg-gray-50">
          Upload document
        </Link>
        <Link href={clientLink} className="rounded-lg border border-gray-200 px-3 py-2.5 text-center text-sm text-gray-600 hover:border-gray-300 hover:bg-gray-50">
          Ask AI
        </Link>
        <Link href={clientLink} className="rounded-lg border border-gray-200 px-3 py-2.5 text-center text-sm text-gray-600 hover:border-gray-300 hover:bg-gray-50">
          Generate brief
        </Link>
        <Link href="/dashboard/settings/integrations" className="rounded-lg border border-gray-200 px-3 py-2.5 text-center text-sm text-gray-600 hover:border-gray-300 hover:bg-gray-50">
          Sync email
        </Link>
      </div>
    </SectionCard>
  );
}

export function UsageCard({
  data,
  showSeats = true,
  showUpgrade = true,
}: {
  data: DashboardSummary;
  showSeats?: boolean;
  showUpgrade?: boolean;
}) {
  const { stats, plan } = data;
  const badgeClass = TIER_BADGE_COLORS[plan.tier] ?? TIER_BADGE_COLORS.free;

  return (
    <SectionCard title="Usage">
      <div className="space-y-3">
        {stats.clients.limit != null && (
          <ThinProgress label="Clients" current={stats.clients.count} max={stats.clients.limit} />
        )}
        {stats.documents.limit != null && (
          <ThinProgress label="Documents" current={stats.documents.count} max={stats.documents.limit} />
        )}
        <ThinProgress label="AI Queries" current={stats.ai_queries.used} max={stats.ai_queries.limit} />
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
            {plan.tier.charAt(0).toUpperCase() + plan.tier.slice(1)}
          </span>
          {showSeats && plan.seats_used != null && plan.seats_total != null && (
            <span className="text-xs text-gray-500">
              {plan.seats_used} of {plan.seats_total} seats
            </span>
          )}
        </div>
        {showUpgrade && (plan.tier === "free" || plan.tier === "starter") && (
          <Link href="/dashboard/settings/subscriptions" className="text-xs text-blue-600 hover:text-blue-800">
            Upgrade
          </Link>
        )}
      </div>
    </SectionCard>
  );
}
