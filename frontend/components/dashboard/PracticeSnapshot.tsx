"use client";

import Link from "next/link";

import type { DashboardSummary } from "@/lib/api";
import ThinProgress from "@/components/ui/ThinProgress";

const TIER_BADGE_COLORS: Record<string, string> = {
  firm: "bg-indigo-100 text-indigo-700",
  professional: "bg-purple-100 text-purple-700",
  starter: "bg-blue-100 text-blue-700",
  free: "bg-gray-100 text-gray-700",
};

interface Props {
  data: DashboardSummary;
}

export default function PracticeSnapshot({ data }: Props) {
  const { stats, plan } = data;
  const badgeClass = TIER_BADGE_COLORS[plan.tier] ?? TIER_BADGE_COLORS.free;

  return (
    <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      <h3 className="text-sm font-semibold text-gray-900">Practice snapshot</h3>

      <div className="mt-4 flex-1 space-y-4">
        {/* AI Queries */}
        <ThinProgress label="AI Queries" current={stats.ai_queries.used} max={stats.ai_queries.limit} />

        {/* Completed this week */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Completed this week</span>
          <span className="text-xs font-medium text-gray-700">
            {stats.action_items.completed_this_week}
          </span>
        </div>

        {/* Active clients */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Active clients</span>
          <span className="text-xs font-medium text-gray-700">
            {stats.clients.count}
            {stats.clients.limit != null && (
              <span className="text-gray-400"> / {stats.clients.limit}</span>
            )}
          </span>
        </div>
      </div>

      {/* Plan badge + manage */}
      <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
          {plan.tier.charAt(0).toUpperCase() + plan.tier.slice(1)}
        </span>
        <Link href="/dashboard/settings/subscriptions" className="text-xs text-gray-500 hover:text-gray-700">
          Manage plan
        </Link>
      </div>
    </div>
  );
}
