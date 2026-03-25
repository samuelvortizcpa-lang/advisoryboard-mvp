"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import type {
  ClientStrategySummary,
  StrategyAdoption,
  StrategyOverview,
  UnreviewedAlert,
} from "@/lib/api";
import { createStrategyDashboardApi } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import SectionCard from "@/components/ui/SectionCard";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 8 }, (_, i) => CURRENT_YEAR - 6 + i);

const CATEGORY_LABELS: Record<string, string> = {
  universal: "Universal",
  business: "Business",
  real_estate: "Real Estate",
  high_income: "High Income",
  estate: "Estate",
  medical: "Medical",
};

const FLAG_LABELS: Record<string, string> = {
  has_business_entity: "Business",
  has_real_estate: "RE",
  is_real_estate_professional: "RE Pro",
  has_high_income: "High Inc.",
  has_estate_planning: "Estate",
  is_medical_professional: "Medical",
  has_retirement_plans: "Retire",
  has_investments: "Invest",
  has_employees: "Employees",
};

function fmtMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}k`;
  return `$${n.toLocaleString()}`;
}

function coverageColor(pct: number): string {
  if (pct >= 75) return "bg-green-500";
  if (pct >= 25) return "bg-amber-500";
  return "bg-red-500";
}

function coverageTrackColor(pct: number): string {
  if (pct >= 75) return "bg-green-100";
  if (pct >= 25) return "bg-amber-100";
  return "bg-red-100";
}

export default function StrategyDashboardPage() {
  const { getToken } = useAuth();
  const [year, setYear] = useState(CURRENT_YEAR);
  const [overview, setOverview] = useState<StrategyOverview | null>(null);
  const [clients, setClients] = useState<ClientStrategySummary[]>([]);
  const [adoption, setAdoption] = useState<StrategyAdoption[]>([]);
  const [alerts, setAlerts] = useState<UnreviewedAlert[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const api = createStrategyDashboardApi(getToken);
      const [ov, cl, ad, al] = await Promise.all([
        api.fetchOverview(year),
        api.fetchClients(year),
        api.fetchAdoption(year),
        api.fetchAlerts(year),
      ]);
      setOverview(ov);
      setClients(cl);
      setAdoption(ad);
      setAlerts(al);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [getToken, year]);

  useEffect(() => {
    load();
  }, [load]);

  // Group alerts by client
  const alertsByClient = new Map<string, UnreviewedAlert[]>();
  for (const a of alerts) {
    const list = alertsByClient.get(a.client_id) ?? [];
    list.push(a);
    alertsByClient.set(a.client_id, list);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Strategy Dashboard</h1>
          <p className="mt-0.5 text-xs text-gray-500">Tax strategy coverage across all clients</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-500">Tax Year</label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 shadow-sm"
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Loading skeleton ──────────────────────────────────────────── */}
      {loading && !overview && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      )}

      {/* ── Stat cards ────────────────────────────────────────────────── */}
      {overview && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Total Clients"
            value={overview.total_clients}
            context={`${overview.clients_reviewed} reviewed`}
            contextType="success"
          />
          <StatCard
            label="Strategies Implemented"
            value={overview.total_implemented}
            context="across all clients"
            contextType="muted"
          />
          <StatCard
            label="Estimated Impact"
            value={fmtMoney(overview.total_estimated_impact)}
            context={`${year} tax year`}
            contextType="muted"
          />
          <StatCard
            label="Clients Needing Review"
            value={overview.clients_unreviewed}
            context={overview.clients_unreviewed > 0 ? "need attention" : "all caught up"}
            contextType={overview.clients_unreviewed > 0 ? "danger" : "success"}
          />
        </div>
      )}

      {/* ── Two-column tables ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Client Coverage */}
        <SectionCard title="Client Coverage">
          {clients.length === 0 && !loading ? (
            <p className="py-6 text-center text-xs text-gray-400">No clients found</p>
          ) : (
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-gray-500">
                    <th className="px-5 py-2 font-medium">Client</th>
                    <th className="px-3 py-2 font-medium">Flags</th>
                    <th className="px-3 py-2 font-medium text-right">Reviewed</th>
                    <th className="px-3 py-2 font-medium text-right">Impl.</th>
                    <th className="px-3 py-2 font-medium text-right">Impact</th>
                    <th className="px-3 py-2 font-medium" style={{ minWidth: 100 }}>Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {clients.map((c) => (
                    <tr
                      key={c.client_id}
                      className="border-b border-gray-50 last:border-b-0 hover:bg-gray-50 cursor-pointer"
                    >
                      <td className="px-5 py-2.5">
                        <Link
                          href={`/dashboard/clients/${c.client_id}?tab=strategies`}
                          className="block"
                        >
                          <div className="flex items-center gap-2">
                            {c.coverage_pct === 0 && c.total_reviewed === 0 && (
                              <svg className="h-3.5 w-3.5 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                              </svg>
                            )}
                            <div>
                              <p className="font-medium text-gray-900">{c.client_name}</p>
                              {c.client_type && (
                                <p className="text-[10px] text-gray-400">{c.client_type}</p>
                              )}
                            </div>
                          </div>
                        </Link>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {c.active_flags.slice(0, 3).map((f) => (
                            <span
                              key={f}
                              className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[9px] font-medium text-blue-600"
                            >
                              {FLAG_LABELS[f] ?? f}
                            </span>
                          ))}
                          {c.active_flags.length > 3 && (
                            <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] text-gray-500">
                              +{c.active_flags.length - 3}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-700">
                        {c.total_reviewed}/{c.total_applicable}
                      </td>
                      <td className="px-3 py-2.5 text-right font-medium text-green-600">
                        {c.total_implemented}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-700">
                        {c.total_estimated_impact > 0 ? fmtMoney(c.total_estimated_impact) : "—"}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className={`h-1.5 flex-1 rounded-full ${coverageTrackColor(c.coverage_pct)}`}>
                            <div
                              className={`h-1.5 rounded-full ${coverageColor(c.coverage_pct)} transition-all`}
                              style={{ width: `${Math.max(c.coverage_pct, 2)}%` }}
                            />
                          </div>
                          <span className="w-8 text-right text-[10px] font-medium text-gray-500">
                            {c.coverage_pct}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        {/* Strategy Adoption */}
        <SectionCard title="Strategy Adoption">
          {adoption.length === 0 && !loading ? (
            <p className="py-6 text-center text-xs text-gray-400">No strategy data yet</p>
          ) : (
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-gray-500">
                    <th className="px-5 py-2 font-medium">Strategy</th>
                    <th className="px-3 py-2 font-medium">Category</th>
                    <th className="px-3 py-2 font-medium text-right">Applicable</th>
                    <th className="px-3 py-2 font-medium text-right">Impl.</th>
                    <th className="px-3 py-2 font-medium text-right">Adoption</th>
                  </tr>
                </thead>
                <tbody>
                  {adoption.map((s) => (
                    <tr key={s.strategy_id} className="border-b border-gray-50 last:border-b-0">
                      <td className="px-5 py-2.5">
                        <p className="font-medium text-gray-900">{s.strategy_name}</p>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">
                          {CATEGORY_LABELS[s.category] ?? s.category}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-700">{s.total_applicable}</td>
                      <td className="px-3 py-2.5 text-right font-medium text-green-600">{s.total_implemented}</td>
                      <td className="px-3 py-2.5 text-right">
                        <span className={`font-medium ${s.adoption_rate >= 50 ? "text-green-600" : s.adoption_rate >= 25 ? "text-amber-600" : "text-red-600"}`}>
                          {s.adoption_rate}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Attention Feed ─────────────────────────────────────────────── */}
      <SectionCard title="Needs Attention">
        {alerts.length === 0 && !loading ? (
          <div className="py-8 text-center">
            <p className="text-sm text-gray-500">
              All client strategies are up to date for {year}!
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {Array.from(alertsByClient.entries()).map(([clientId, clientAlerts]) => (
              <div key={clientId} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <Link
                  href={`/dashboard/clients/${clientId}?tab=strategies`}
                  className="block"
                >
                  <p className="mb-1.5 text-xs font-semibold text-gray-900">
                    {clientAlerts[0].client_name}
                  </p>
                  <div className="space-y-1">
                    {clientAlerts.map((a) => (
                      <div key={a.strategy_id} className="flex items-center gap-2 text-xs text-gray-600">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                        <span>{a.strategy_name}</span>
                        <span className="rounded-full bg-gray-200 px-1.5 py-0.5 text-[9px] text-gray-500">
                          {CATEGORY_LABELS[a.category] ?? a.category}
                        </span>
                      </div>
                    ))}
                  </div>
                </Link>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
