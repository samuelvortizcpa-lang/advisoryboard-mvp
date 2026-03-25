"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import type { StrategyHistory } from "@/lib/api";
import { createStrategiesApi } from "@/lib/api";

interface Props {
  clientId: string;
}

const STATUS_ICONS: Record<string, { bg: string; label: string }> = {
  not_reviewed: { bg: "bg-gray-300", label: "Not Reviewed" },
  recommended: { bg: "bg-blue-500", label: "Recommended" },
  implemented: { bg: "bg-green-500", label: "Implemented" },
  not_applicable: { bg: "bg-gray-200", label: "Not Applicable" },
  declined: { bg: "bg-orange-400", label: "Declined" },
};

const CATEGORY_LABELS: Record<string, string> = {
  universal: "Universal Strategies",
  business: "Business Strategies",
  real_estate: "Real Estate Strategies",
  high_income: "High Income Strategies",
  estate: "Estate Planning Strategies",
  medical: "Medical Professional Strategies",
};

function fmtMoney(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k`;
  return `$${n.toLocaleString()}`;
}

export default function StrategyComparison({ clientId }: Props) {
  const { getToken } = useAuth();
  const [data, setData] = useState<StrategyHistory | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const api = createStrategiesApi(getToken);
      const result = await api.fetchHistory(clientId);
      setData(result);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [getToken, clientId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="mt-4 space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-xl border border-gray-200 bg-white" />
        ))}
      </div>
    );
  }

  if (!data || data.strategies.length === 0) {
    return (
      <div className="mt-4 rounded-xl border border-gray-200 bg-white px-6 py-12 text-center shadow-sm">
        <p className="text-sm text-gray-500">No strategy history found for this client.</p>
        <p className="mt-1 text-xs text-gray-400">
          Update strategy statuses on the Current Year view to build history.
        </p>
      </div>
    );
  }

  const years = data.available_years.sort((a, b) => a - b);

  // Group strategies by category
  const grouped = new Map<string, StrategyHistory["strategies"]>();
  for (const s of data.strategies) {
    const list = grouped.get(s.category) ?? [];
    list.push(s);
    grouped.set(s.category, list);
  }

  return (
    <div className="mt-4 space-y-4">
      {/* ── Year summaries ──────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="px-4 py-2 text-left font-medium text-gray-500">Summary</th>
              {years.map((y) => (
                <th key={y} className="min-w-[80px] px-3 py-2 text-center font-medium text-gray-500">
                  {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.year_summaries.length > 0 && (
              <>
                <tr className="border-b border-gray-50">
                  <td className="px-4 py-2 text-gray-600">Implemented</td>
                  {years.map((y) => {
                    const s = data.year_summaries.find((ys) => ys.tax_year === y);
                    return (
                      <td key={y} className="px-3 py-2 text-center font-medium text-green-600">
                        {s?.total_implemented ?? "—"}
                      </td>
                    );
                  })}
                </tr>
                <tr className="border-b border-gray-50">
                  <td className="px-4 py-2 text-gray-600">Reviewed</td>
                  {years.map((y) => {
                    const s = data.year_summaries.find((ys) => ys.tax_year === y);
                    return (
                      <td key={y} className="px-3 py-2 text-center text-gray-700">
                        {s ? `${s.total_reviewed}/${s.total_applicable}` : "—"}
                      </td>
                    );
                  })}
                </tr>
                <tr>
                  <td className="px-4 py-2 text-gray-600">Est. Impact</td>
                  {years.map((y) => {
                    const s = data.year_summaries.find((ys) => ys.tax_year === y);
                    return (
                      <td key={y} className="px-3 py-2 text-center font-medium text-blue-600">
                        {s && s.total_estimated_impact > 0
                          ? fmtMoney(s.total_estimated_impact)
                          : "—"}
                      </td>
                    );
                  })}
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Strategy grid by category ──────────────────────────────── */}
      {Array.from(grouped.entries()).map(([category, strategies]) => (
        <div key={category} className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-2.5 text-left text-sm font-semibold text-gray-900">
                  {CATEGORY_LABELS[category] ?? category}
                  <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500">
                    {strategies.length}
                  </span>
                </th>
                {years.map((y) => (
                  <th key={y} className="min-w-[80px] px-3 py-2.5 text-center font-medium text-gray-500">
                    {y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strategies.map((s) => (
                <tr key={s.strategy_id} className="border-b border-gray-50 last:border-b-0">
                  <td className="px-4 py-2.5">
                    <p className="font-medium text-gray-900">{s.name}</p>
                  </td>
                  {years.map((y) => {
                    const yearStatus = s.statuses.find((st) => st.tax_year === y);
                    const status = yearStatus?.status ?? "not_reviewed";
                    const info = STATUS_ICONS[status] ?? STATUS_ICONS.not_reviewed;
                    return (
                      <td key={y} className="px-3 py-2.5 text-center">
                        <div className="group relative inline-flex items-center justify-center">
                          <span
                            className={`inline-block h-3 w-3 rounded-full ${info.bg}`}
                          />
                          {/* Tooltip */}
                          <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-[10px] text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                            {info.label}
                            {yearStatus?.estimated_impact != null && yearStatus.estimated_impact > 0 && (
                              <span className="ml-1 text-green-300">
                                {fmtMoney(yearStatus.estimated_impact)}
                              </span>
                            )}
                            {yearStatus?.notes && (
                              <div className="mt-0.5 max-w-[200px] truncate text-gray-300">
                                {yearStatus.notes}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {/* ── Legend ──────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-4 px-1 text-xs text-gray-500">
        {Object.entries(STATUS_ICONS).map(([key, { bg, label }]) => (
          <div key={key} className="flex items-center gap-1.5">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${bg}`} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
