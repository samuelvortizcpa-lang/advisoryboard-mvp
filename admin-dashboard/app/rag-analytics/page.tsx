"use client";

import { useEffect, useState } from "react";

// ─── API ────────────────────────────────────────────────────────────────────

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "https://advisoryboard-mvp-production.up.railway.app"}/api`;

interface EvalSummary {
  total_runs: number;
  latest_run: {
    evaluation_id: string;
    client_id: string;
    created_at: string;
    retrieval_hit_rate: number;
    response_keyword_rate: number;
    avg_latency_ms: number;
  } | null;
  avg_retrieval_hit_rate: number | null;
  avg_response_keyword_rate: number | null;
  avg_latency_ms: number | null;
  trend: {
    date: string;
    evaluation_id: string;
    retrieval_hit_rate: number;
    response_keyword_rate: number;
    avg_latency_ms: number;
  }[];
}

interface EvalListItem {
  evaluation_id: string;
  client_id: string;
  client_name: string | null;
  created_at: string;
  retrieval_hit_rate: number;
  response_keyword_rate: number;
  avg_latency_ms: number;
  total_questions: number;
  commit_sha: string | null;
}

async function apiFetch<T>(token: string | null, path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { "X-Admin-Key": token } : {},
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function fmtMs(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${(n / 1000).toFixed(1)}s`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ─── Components ─────────────────────────────────────────────────────────────

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function RagAnalyticsPage() {
  const token = process.env.NEXT_PUBLIC_ADMIN_TOKEN ?? null;
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [evals, setEvals] = useState<EvalListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    async function load() {
      try {
        const [s, e] = await Promise.all([
          apiFetch<EvalSummary>(token, "/admin/rag-analytics/summary?days=30"),
          apiFetch<EvalListItem[]>(token, "/admin/rag-analytics/evaluations?limit=20"),
        ]);
        if (!cancelled) {
          setSummary(s);
          setEvals(e);
        }
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // ── No token ──────────────────────────────────────────────────────────

  if (!token) {
    return (
      <div className="px-8 py-8">
        <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-8 text-center">
          <p className="text-sm font-medium text-yellow-800">
            Set NEXT_PUBLIC_ADMIN_TOKEN in .env.local
          </p>
        </div>
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="px-8 py-8">
        <div className="rounded-xl border border-red-200 bg-white p-8 text-center">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  // ── Loading ───────────────────────────────────────────────────────────

  if (!summary) {
    return (
      <div className="px-8 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-6 w-48 rounded bg-gray-200" />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-gray-200 bg-white p-5"
              >
                <div className="h-3 w-16 rounded bg-gray-200" />
                <div className="mt-3 h-7 w-20 rounded bg-gray-200" />
              </div>
            ))}
          </div>
          <div className="h-64 rounded-xl border border-gray-200 bg-white" />
        </div>
      </div>
    );
  }

  // ── Empty state ───────────────────────────────────────────────────────

  if (summary.total_runs === 0) {
    return (
      <div className="px-8 py-8 space-y-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
            Admin
          </p>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">
            RAG Analytics
          </h1>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
          <p className="text-sm text-gray-500">
            No eval runs yet — click Run Eval to start
          </p>
        </div>
      </div>
    );
  }

  // ── Main render ───────────────────────────────────────────────────────

  const { latest_run } = summary;

  return (
    <div className="px-8 py-8 space-y-6">
      {/* Header */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Admin
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">
          RAG Analytics
        </h1>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard
          label="Total Eval Runs"
          value={String(summary.total_runs)}
        />
        <MetricCard
          label="Latest Retrieval"
          value={fmtPct(latest_run?.retrieval_hit_rate)}
        />
        <MetricCard
          label="Latest Keyword"
          value={fmtPct(latest_run?.response_keyword_rate)}
        />
        <MetricCard
          label="Avg Latency"
          value={fmtMs(latest_run?.avg_latency_ms)}
        />
        <MetricCard
          label="30-Day Avg Retrieval"
          value={fmtPct(summary.avg_retrieval_hit_rate)}
        />
        <MetricCard
          label="30-Day Avg Keyword"
          value={fmtPct(summary.avg_response_keyword_rate)}
        />
      </div>

      {/* Trend chart placeholder */}
      {summary.trend.length > 1 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">
            Eval Trend (last 30 days)
          </h2>
          <div className="flex items-end gap-1" style={{ height: 120 }}>
            {summary.trend.map((point) => {
              const h = Math.max(4, Math.round((point.retrieval_hit_rate ?? 0) * 100));
              return (
                <div
                  key={point.evaluation_id}
                  className="flex-1 rounded-t bg-blue-500 transition-all hover:bg-blue-600"
                  style={{ height: `${h}%` }}
                  title={`${fmtDate(point.date)}: ${fmtPct(point.retrieval_hit_rate)} retrieval, ${fmtPct(point.response_keyword_rate)} keyword`}
                />
              );
            })}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-gray-400">
            <span>{fmtDate(summary.trend[0].date)}</span>
            <span>{fmtDate(summary.trend[summary.trend.length - 1].date)}</span>
          </div>
        </div>
      )}

      {/* Eval history table */}
      {evals && evals.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-100 px-5 py-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Recent Evaluations
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-[11px] font-medium uppercase tracking-wider text-gray-400">
                  <th className="px-5 py-2">Date</th>
                  <th className="px-5 py-2">Client</th>
                  <th className="px-5 py-2">Questions</th>
                  <th className="px-5 py-2">Retrieval</th>
                  <th className="px-5 py-2">Keyword</th>
                  <th className="px-5 py-2">Latency</th>
                </tr>
              </thead>
              <tbody>
                {evals.map((e) => (
                  <tr
                    key={e.evaluation_id}
                    className="border-b border-gray-50 hover:bg-gray-50"
                  >
                    <td className="px-5 py-2 text-gray-600">
                      {fmtDate(e.created_at)}
                    </td>
                    <td className="px-5 py-2 font-medium text-gray-900">
                      {e.client_name ?? e.client_id.slice(0, 8)}
                    </td>
                    <td className="px-5 py-2 text-gray-600">
                      {e.total_questions}
                    </td>
                    <td className="px-5 py-2 font-medium text-gray-900">
                      {fmtPct(e.retrieval_hit_rate)}
                    </td>
                    <td className="px-5 py-2 font-medium text-gray-900">
                      {fmtPct(e.response_keyword_rate)}
                    </td>
                    <td className="px-5 py-2 text-gray-600">
                      {fmtMs(e.avg_latency_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
