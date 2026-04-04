"use client";

import Link from "next/link";
import { ResponsiveContainer, AreaChart, Area } from "recharts";

import type { RevenueImpact } from "@/lib/api";

interface Props {
  data: RevenueImpact | null;
}

const fmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export default function RevenueImpactCard({ data }: Props) {
  // Loading state
  if (!data) {
    return (
      <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center gap-2">
          <div className="h-4 w-36 rounded bg-gray-200" />
          <div className="h-4 w-4 rounded bg-gray-100" />
        </div>
        <div className="mt-3 h-8 w-28 rounded bg-gray-200" />
        <div className="mt-2 h-3 w-44 rounded bg-gray-100" />
        <div className="mt-4 h-10 w-full rounded bg-gray-50" />
        <div className="mt-4 h-3 w-40 rounded bg-gray-100" />
      </div>
    );
  }

  const hasImpact = data.total_estimated_savings > 0;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      {/* Header */}
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium text-gray-500">Client savings this year</h3>
        {/* TrendingUp icon */}
        <svg
          className="h-4 w-4 text-green-500"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
          <polyline points="16 7 22 7 22 13" />
        </svg>
      </div>

      {/* Primary metric */}
      <p className={`mt-2 text-[28px] font-semibold leading-tight ${hasImpact ? "text-gray-900" : "text-gray-300"}`}>
        {fmt.format(data.total_estimated_savings)}
      </p>

      {/* Subtitle */}
      <p className="mt-1 text-xs text-gray-500">
        across {data.clients_impacted} client{data.clients_impacted !== 1 ? "s" : ""}
        {" \u00B7 "}
        {data.strategies_implemented} strateg{data.strategies_implemented !== 1 ? "ies" : "y"} implemented
      </p>

      {/* Sparkline */}
      {data.monthly_trend.length > 0 && (
        <div className="mt-3" style={{ width: "100%", height: 40 }}>
          <ResponsiveContainer width="100%" height={40}>
            <AreaChart data={data.monthly_trend} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#22c55e" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="amount"
                stroke="#22c55e"
                strokeWidth={1.5}
                fill="url(#revGrad)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Bottom link */}
      <div className="mt-3 border-t border-gray-100 pt-3">
        <Link
          href="/dashboard/strategy-dashboard"
          className="text-xs font-medium text-blue-600 hover:text-blue-800"
        >
          {hasImpact ? "View strategy dashboard \u2192" : "Start reviewing strategies \u2192"}
        </Link>
      </div>
    </div>
  );
}
