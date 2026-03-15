"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { UsageSummary, createUsageApi } from "@/lib/api";

export default function UsageStats() {
  const { getToken } = useAuth();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    createUsageApi(getToken)
      .summary(30)
      .then(setUsage)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          AI Usage This Month
        </h2>
        <p className="mt-3 text-sm text-gray-400">Usage data unavailable</p>
      </div>
    );
  }

  if (loading || !usage) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm animate-pulse">
        <div className="h-3 w-32 rounded bg-gray-200" />
        <div className="mt-4 grid grid-cols-3 gap-4">
          <div className="h-14 rounded-lg bg-gray-100" />
          <div className="h-14 rounded-lg bg-gray-100" />
          <div className="h-14 rounded-lg bg-gray-100" />
        </div>
      </div>
    );
  }

  // Compute quick vs deep counts from query_type breakdown
  const quickCount =
    usage.breakdown_by_query_type.find((b) => b.query_type === "factual")
      ?.queries ?? 0;
  const deepCount =
    usage.breakdown_by_query_type.find((b) => b.query_type === "strategic")
      ?.queries ?? 0;
  const otherCount = usage.total_queries - quickCount - deepCount;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
        AI Usage This Month
      </h2>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Total queries */}
        <div className="rounded-lg border border-gray-100 bg-gray-50 px-5 py-4">
          <p className="text-2xl font-bold text-gray-900">
            {usage.total_queries}
          </p>
          <p className="mt-0.5 text-sm text-gray-500">AI Queries</p>
        </div>

        {/* Estimated cost */}
        <div className="rounded-lg border border-gray-100 bg-gray-50 px-5 py-4">
          <p className="text-2xl font-bold text-gray-900">
            ${usage.total_cost.toFixed(2)}
          </p>
          <p className="mt-0.5 text-sm text-gray-500">Estimated Cost</p>
        </div>

        {/* Tokens */}
        <div className="rounded-lg border border-gray-100 bg-gray-50 px-5 py-4">
          <p className="text-2xl font-bold text-gray-900">
            {usage.total_tokens.toLocaleString()}
          </p>
          <p className="mt-0.5 text-sm text-gray-500">Tokens Used</p>
        </div>
      </div>

      {/* Breakdown bar */}
      {usage.total_queries > 0 && (
        <div className="mt-4">
          <div className="flex h-2 overflow-hidden rounded-full bg-gray-100">
            {quickCount > 0 && (
              <div
                className="bg-blue-400"
                style={{
                  width: `${(quickCount / usage.total_queries) * 100}%`,
                }}
              />
            )}
            {deepCount > 0 && (
              <div
                className="bg-purple-400"
                style={{
                  width: `${(deepCount / usage.total_queries) * 100}%`,
                }}
              />
            )}
            {otherCount > 0 && (
              <div
                className="bg-gray-300"
                style={{
                  width: `${(otherCount / usage.total_queries) * 100}%`,
                }}
              />
            )}
          </div>
          <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-blue-400" />
              {quickCount} Quick Lookup{quickCount !== 1 ? "s" : ""}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-purple-400" />
              {deepCount} Deep Analys{deepCount !== 1 ? "es" : "is"}
            </span>
            {otherCount > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-gray-300" />
                {otherCount} Other
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
