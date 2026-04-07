"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useState, useCallback } from "react";

import {
  createUsageApi,
  UsageSummary,
  SubscriptionInfo,
  DailyUsageItem,
  ClientUsageItem,
  UsageHistoryResponse,
} from "@/lib/api";
import HelpTooltip from "@/components/ui/HelpTooltip";

// ─── Formatting helpers ─────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtDateTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }) + " " + d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function fmtCost(n: number, decimals = 2) {
  return "$" + n.toFixed(decimals);
}

function fmtTokens(n: number) {
  return n.toLocaleString();
}

// ─── Constants ──────────────────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
] as const;

const ENDPOINT_LABELS: Record<string, string> = {
  chat: "Chat",
  brief: "Brief",
  document_classify: "Classify",
  classify: "Classify",
  action_items: "Action Items",
};

const ENDPOINT_COLORS: Record<string, string> = {
  chat: "bg-blue-100 text-blue-700",
  brief: "bg-green-100 text-green-700",
  document_classify: "bg-orange-100 text-orange-700",
  classify: "bg-orange-100 text-orange-700",
  action_items: "bg-gray-100 text-gray-600",
};

function modelLabel(m: string) {
  const ml = m.toLowerCase();
  if (ml.includes("opus")) return "Premium";
  if (ml.includes("sonnet") || ml.includes("claude")) return "Advanced";
  return "Standard";
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function UsageAnalyticsPage() {
  const { getToken } = useAuth();

  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [daily, setDaily] = useState<DailyUsageItem[]>([]);
  const [clientUsage, setClientUsage] = useState<ClientUsageItem[]>([]);
  const [history, setHistory] = useState<UsageHistoryResponse | null>(null);

  // History filters
  const [historyPage, setHistoryPage] = useState(1);
  const [historyModel, setHistoryModel] = useState("");
  const [historyEndpoint, setHistoryEndpoint] = useState("");

  // Chart tooltip
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);

  // Export loading
  const [exporting, setExporting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createUsageApi(getToken);
      const [s, sub, d, c] = await Promise.all([
        api.summary(days),
        api.subscription(),
        api.daily(days),
        api.byClient(days),
      ]);
      setSummary(s);
      setSubscription(sub);
      setDaily(d);
      setClientUsage(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load usage data");
    } finally {
      setLoading(false);
    }
  }, [getToken, days]);

  const loadHistory = useCallback(async () => {
    try {
      const api = createUsageApi(getToken);
      const h = await api.history({
        page: historyPage,
        per_page: 50,
        model: historyModel || undefined,
        endpoint: historyEndpoint || undefined,
      });
      setHistory(h);
    } catch {
      // non-fatal
    }
  }, [getToken, historyPage, historyModel, historyEndpoint]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  async function handleExport() {
    setExporting(true);
    try {
      await createUsageApi(getToken).exportCsv();
    } catch {
      // silent
    } finally {
      setExporting(false);
    }
  }

  // ── Loading skeleton ────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6 animate-pulse">
        <div className="mx-auto max-w-6xl space-y-6">
          <div className="h-8 w-48 rounded bg-gray-200" />
          <div className="h-4 w-72 rounded bg-gray-200" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-white border border-gray-200 shadow-sm" />
            ))}
          </div>
          <div className="h-64 rounded-xl bg-white border border-gray-200 shadow-sm" />
          <div className="h-48 rounded-xl bg-white border border-gray-200 shadow-sm" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-600">{error}</p>
            <button onClick={loadData} className="mt-3 text-sm font-medium text-red-700 hover:underline">
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!summary || !subscription) return null;

  const avgCost = summary.total_queries > 0 ? summary.total_cost / summary.total_queries : 0;
  const quotaUsed = subscription.total_queries_used;
  const quotaLimit = subscription.total_queries_limit;
  const quotaPct = quotaLimit > 0 ? Math.min(100, (quotaUsed / quotaLimit) * 100) : 0;

  // Chart data
  const maxQueries = Math.max(1, ...daily.map((d) => d.total_queries));
  const allModels = Array.from(
    new Set(daily.flatMap((d) => Object.keys(d.by_model)))
  );
  function modelColor(m: string) {
    const ml = m.toLowerCase();
    if (ml.includes("opus")) return "bg-purple-400";
    if (ml.includes("sonnet") || ml.includes("claude")) return "bg-blue-400";
    return "bg-gray-400";
  }

  // Model breakdown from summary
  const modelBreakdown = summary.breakdown_by_model ?? [];
  const totalModelCost = modelBreakdown.reduce((a, b) => a + b.cost, 0) || 1;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl space-y-6">

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Usage Analytics</h1>
            <p className="mt-1 text-sm text-gray-500">
              {subscription.billing_period_start && subscription.billing_period_end
                ? `${fmtDate(subscription.billing_period_start)} \u2013 ${fmtDate(subscription.billing_period_end)}`
                : "Current billing period"
              }
              {" \u00b7 "}
              <span className="font-medium capitalize text-gray-700">{subscription.tier}</span> plan
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Period pills */}
            <div className="flex rounded-lg border border-gray-200 bg-white p-0.5">
              {PERIOD_OPTIONS.map((opt) => (
                <button
                  key={opt.days}
                  onClick={() => { setDays(opt.days); setHistoryPage(1); }}
                  className={[
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    days === opt.days
                      ? "bg-blue-600 text-white"
                      : "text-gray-500 hover:text-gray-700",
                  ].join(" ")}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {/* Export */}
            <button
              onClick={handleExport}
              disabled={exporting}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z" />
                <path d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z" />
              </svg>
              {exporting ? "Exporting\u2026" : "Export CSV"}
            </button>
          </div>
        </div>

        {/* ── Summary Cards ───────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard label="Total Queries" value={fmtTokens(summary.total_queries)} />
          <SummaryCard label="Total Cost" value={fmtCost(summary.total_cost)} labelExtra={<HelpTooltip content="Your AI cost varies by analysis tier. Standard queries cost less, while advanced and premium analyses use more powerful capabilities." position="bottom" maxWidth={260} />} />
          <SummaryCard label="Avg Cost / Query" value={fmtCost(avgCost, 4)} />
          <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
            <p className="text-xs font-medium text-gray-500">AI Queries</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {quotaUsed} <span className="text-sm font-normal text-gray-400">of {quotaLimit}</span>
            </p>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
              <div
                className={`h-full rounded-full transition-all ${quotaPct > 80 ? "bg-orange-400" : "bg-blue-400"}`}
                style={{ width: `${quotaPct}%` }}
              />
            </div>
          </div>
        </div>

        {/* ── Daily Usage Chart ────────────────────────────────────────────── */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">Daily Usage</h2>
          <div className="relative mt-4 flex items-end gap-px" style={{ height: 200 }}>
            {daily.map((d, i) => {
              const total = d.total_queries;
              const barH = maxQueries > 0 ? (total / maxQueries) * 100 : 0;

              // Stack segments per model
              const segments = allModels.map((m) => ({
                model: m,
                queries: d.by_model[m]?.queries ?? 0,
              }));

              return (
                <div
                  key={d.date}
                  className="group relative flex flex-1 flex-col justify-end"
                  style={{ height: "100%" }}
                  onMouseEnter={() => setHoveredBar(i)}
                  onMouseLeave={() => setHoveredBar(null)}
                >
                  {/* Tooltip */}
                  {hoveredBar === i && (
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg">
                      <p className="font-semibold text-gray-900">{fmtDate(d.date)}</p>
                      <p className="text-gray-500">{total} queries &middot; {fmtCost(d.total_cost, 4)}</p>
                      {segments.map((s) =>
                        s.queries > 0 ? (
                          <p key={s.model} className="text-gray-500">
                            {modelLabel(s.model)}: {s.queries}
                          </p>
                        ) : null
                      )}
                    </div>
                  )}
                  {/* Bar */}
                  <div
                    className="flex w-full flex-col overflow-hidden rounded-t"
                    style={{ height: `${barH}%`, minHeight: total > 0 ? 2 : 0 }}
                  >
                    {segments.map((s) => {
                      const segPct = total > 0 ? (s.queries / total) * 100 : 0;
                      return (
                        <div
                          key={s.model}
                          className={modelColor(s.model)}
                          style={{ height: `${segPct}%` }}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          {/* X-axis labels — show ~5 labels */}
          <div className="mt-2 flex justify-between text-[10px] text-gray-400">
            {daily.length > 0 && <span>{fmtDate(daily[0].date)}</span>}
            {daily.length > 1 && <span>{fmtDate(daily[daily.length - 1].date)}</span>}
          </div>
          {/* Legend */}
          <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-gray-400" /> Standard
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-blue-400" /> Advanced
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-purple-400" /> Premium
            </span>
          </div>
        </div>

        {/* ── Model Breakdown ─────────────────────────────────────────────── */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">Cost Breakdown by Tier</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {modelBreakdown.map((m) => (
              <div key={m.model} className="rounded-lg border border-gray-100 bg-gray-50 p-4">
                <p className="text-sm font-semibold text-gray-900">{modelLabel(m.model)}</p>
                <div className="mt-2 grid grid-cols-2 gap-y-1 text-xs">
                  <span className="text-gray-500">Queries</span>
                  <span className="text-right font-medium text-gray-700">{fmtTokens(m.queries)}</span>
                  <span className="text-gray-500">Tokens</span>
                  <span className="text-right font-medium text-gray-700">{fmtTokens(m.tokens)}</span>
                  <span className="text-gray-500">Total Cost</span>
                  <span className="text-right font-medium text-gray-700">{fmtCost(m.cost, 4)}</span>
                  <span className="text-gray-500">Avg / Query</span>
                  <span className="text-right font-medium text-gray-700">
                    {m.queries > 0 ? fmtCost(m.cost / m.queries, 4) : "$0.0000"}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {/* Cost split bar */}
          {modelBreakdown.length > 1 && (
            <div className="mt-4">
              <div className="flex h-2 overflow-hidden rounded-full bg-gray-100">
                {modelBreakdown.map((m) => (
                  <div
                    key={m.model}
                    className={modelColor(m.model)}
                    style={{ width: `${(m.cost / totalModelCost) * 100}%` }}
                  />
                ))}
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] text-gray-400">
                {modelBreakdown.map((m) => (
                  <span key={m.model}>
                    {modelLabel(m.model)}: {((m.cost / totalModelCost) * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Top Clients by Cost ─────────────────────────────────────────── */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">Top Clients by Cost</h2>
          {clientUsage.length === 0 ? (
            <p className="mt-4 text-sm text-gray-400">No client usage data for this period.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-gray-400">
                    <th className="pb-2 pr-4">Client</th>
                    <th className="pb-2 pr-4 text-right">Queries</th>
                    <th className="pb-2 pr-4 text-right">Tokens</th>
                    <th className="pb-2 pr-4 text-right">Cost</th>
                    <th className="pb-2 text-right">Last Query</th>
                  </tr>
                </thead>
                <tbody>
                  {clientUsage.slice(0, 10).map((c) => (
                    <tr key={c.client_id} className="border-b border-gray-50">
                      <td className="py-2.5 pr-4">
                        <Link
                          href={`/dashboard/clients/${c.client_id}`}
                          className="font-medium text-blue-600 hover:underline"
                        >
                          {c.client_name}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4 text-right text-gray-700">{fmtTokens(c.total_queries)}</td>
                      <td className="py-2.5 pr-4 text-right text-gray-700">{fmtTokens(c.total_tokens)}</td>
                      <td className="py-2.5 pr-4 text-right font-medium text-gray-900">{fmtCost(c.total_cost, 4)}</td>
                      <td className="py-2.5 text-right text-gray-500">{fmtDate(c.last_query_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Usage History ────────────────────────────────────────────────── */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-sm font-semibold text-gray-900">Usage History</h2>
            <div className="flex items-center gap-2">
              <select
                value={historyModel}
                onChange={(e) => { setHistoryModel(e.target.value); setHistoryPage(1); }}
                className="rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">All Tiers</option>
                <option value="gpt-4o-mini">Standard</option>
                <option value="claude-sonnet-4-20250514">Advanced</option>
                <option value="claude-opus-4-20250514">Premium</option>
              </select>
              <select
                value={historyEndpoint}
                onChange={(e) => { setHistoryEndpoint(e.target.value); setHistoryPage(1); }}
                className="rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">All Types</option>
                <option value="chat">Chat</option>
                <option value="brief">Brief</option>
                <option value="document_classify">Classify</option>
                <option value="action_items">Action Items</option>
              </select>
            </div>
          </div>

          {!history ? (
            <div className="mt-4 animate-pulse space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-10 rounded bg-gray-100" />
              ))}
            </div>
          ) : history.items.length === 0 ? (
            <p className="mt-4 text-sm text-gray-400">No usage records found.</p>
          ) : (
            <>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-gray-400">
                      <th className="pb-2 pr-4">Date/Time</th>
                      <th className="pb-2 pr-4">Type</th>
                      <th className="pb-2 pr-4">Tier</th>
                      <th className="pb-2 pr-4 text-right">Tokens</th>
                      <th className="pb-2 pr-4 text-right">Cost</th>
                      <th className="pb-2">Client</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.items.map((item) => (
                      <tr key={item.id} className="border-b border-gray-50">
                        <td className="whitespace-nowrap py-2.5 pr-4 text-gray-700">
                          {fmtDateTime(item.created_at)}
                        </td>
                        <td className="py-2.5 pr-4">
                          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${ENDPOINT_COLORS[item.endpoint ?? ""] ?? "bg-gray-100 text-gray-600"}`}>
                            {ENDPOINT_LABELS[item.endpoint ?? ""] ?? item.endpoint ?? "\u2014"}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 text-gray-700">{modelLabel(item.model)}</td>
                        <td className="py-2.5 pr-4 text-right text-gray-700">{fmtTokens(item.total_tokens)}</td>
                        <td className="py-2.5 pr-4 text-right font-medium text-gray-900">{fmtCost(item.estimated_cost, 4)}</td>
                        <td className="py-2.5 text-gray-500">{item.client_name ?? "\u2014"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="mt-4 flex items-center justify-between text-xs text-gray-500">
                <span>
                  Page {history.page} of {history.total_pages} ({history.total} records)
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                    disabled={history.page <= 1}
                    className="rounded-md border border-gray-200 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setHistoryPage((p) => Math.min(history.total_pages, p + 1))}
                    disabled={history.page >= history.total_pages}
                    className="rounded-md border border-gray-200 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function SummaryCard({ label, value, labelExtra }: { label: string; value: string; labelExtra?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
      <p className="flex items-center gap-1 text-xs font-medium text-gray-500">{label}{labelExtra}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
