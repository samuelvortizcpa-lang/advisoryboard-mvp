"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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

interface EvalDetail {
  evaluation_id: string;
  client_id: string;
  created_at: string;
  summary: {
    retrieval_hit_rate: number | null;
    response_keyword_rate: number | null;
    avg_latency_ms: number | null;
    total_questions: number | null;
    errors: number;
    test_set: string | null;
  };
  per_question: {
    question: string;
    expected: string[] | null;
    response_snippet: string;
    retrieval_hit: boolean;
    response_hit: boolean;
    latency_ms: number | null;
  }[];
}

interface RunEvalResponse {
  evaluation_id: string;
  summary: {
    retrieval_hit_rate: number | null;
    response_keyword_rate: number | null;
  };
}

// TODO: Replace with a real admin clients endpoint when available
const EVAL_CLIENTS = [
  { id: "92574da3-13ca-4017-a233-54c99d2ae2ae", name: "Michael Tjahjadi" },
] as const;

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

async function apiPost<T>(
  token: string | null,
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Admin-Key": token } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
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

function EvalDetailModal({
  detail,
  loading,
  error,
  onClose,
}: {
  detail: EvalDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="relative w-full bg-white rounded-2xl shadow-2xl mx-4 flex flex-col"
        style={{ maxWidth: 900, maxHeight: "85vh" }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 text-xl leading-none z-10"
        >
          ✕
        </button>

        {/* Loading */}
        {loading && (
          <div className="p-12 text-center">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
            <p className="mt-3 text-sm text-gray-500">Loading evaluation…</p>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="p-12 text-center">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {/* Detail */}
        {detail && !loading && (
          <>
            {/* Header */}
            <div className="border-b border-gray-100 px-6 py-4 pr-12">
              <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
                Evaluation Detail
              </p>
              <h2 className="mt-1 text-lg font-bold text-gray-900">
                {detail.evaluation_id.slice(0, 8)}…
                <span className="ml-3 text-sm font-normal text-gray-500">
                  {fmtDate(detail.created_at)}
                </span>
              </h2>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-2 gap-3 px-6 py-4 sm:grid-cols-4">
              <MetricCard
                label="Questions"
                value={String(detail.summary.total_questions ?? 0)}
              />
              <MetricCard
                label="Retrieval Hit Rate"
                value={fmtPct(detail.summary.retrieval_hit_rate)}
              />
              <MetricCard
                label="Keyword Hit Rate"
                value={fmtPct(detail.summary.response_keyword_rate)}
              />
              <MetricCard
                label="Avg Latency"
                value={fmtMs(detail.summary.avg_latency_ms)}
              />
            </div>

            {/* Per-question cards */}
            <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-3">
              {detail.per_question.map((q, i) => {
                const passed = q.retrieval_hit && q.response_hit;
                return (
                  <div
                    key={i}
                    className="rounded-lg border border-gray-200 p-4"
                    style={{
                      borderLeftWidth: 4,
                      borderLeftColor: passed ? "#22c55e" : "#ef4444",
                    }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <p className="text-sm font-semibold text-gray-900">
                        {q.question}
                      </p>
                      {q.latency_ms != null && (
                        <span className="shrink-0 text-xs text-gray-400">
                          {fmtMs(q.latency_ms)}
                        </span>
                      )}
                    </div>

                    {q.response_snippet && (
                      <p className="mt-2 text-xs text-gray-500 line-clamp-3">
                        {q.response_snippet}
                      </p>
                    )}

                    <div className="mt-3 flex items-center gap-3">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          q.retrieval_hit
                            ? "bg-green-50 text-green-700"
                            : "bg-red-50 text-red-700"
                        }`}
                      >
                        {q.retrieval_hit ? "✓" : "✗"} Retrieval
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          q.response_hit
                            ? "bg-green-50 text-green-700"
                            : "bg-red-50 text-red-700"
                        }`}
                      >
                        {q.response_hit ? "✓" : "✗"} Keyword
                      </span>
                    </div>

                    {q.expected && q.expected.length > 0 && (
                      <p className="mt-2 text-[11px] text-gray-400">
                        Expected: {q.expected.join(", ")}
                      </p>
                    )}
                  </div>
                );
              })}

              {detail.per_question.length === 0 && (
                <p className="py-8 text-center text-sm text-gray-400">
                  No per-question data available
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function RunEvalModal({
  token,
  onClose,
  onSuccess,
}: {
  token: string;
  onClose: () => void;
  onSuccess: (evalId: string, retrieval: number | null, keyword: number | null) => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [clientId, setClientId] = useState<string>(EVAL_CLIENTS[0].id);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !running) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, running]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 180_000);

    try {
      const result = await apiPost<RunEvalResponse>(
        token,
        "/admin/rag-analytics/run-eval",
        { client_id: clientId },
        controller.signal,
      );
      clearTimeout(timeout);
      onSuccess(
        result.evaluation_id,
        result.summary.retrieval_hit_rate,
        result.summary.response_keyword_rate,
      );
    } catch (err) {
      clearTimeout(timeout);
      if (err instanceof DOMException && err.name === "AbortError") {
        setRunError("Eval timed out after 180s — check server logs");
      } else {
        setRunError(err instanceof Error ? err.message : "Eval failed");
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === overlayRef.current && !running) onClose();
      }}
    >
      <div
        className="relative w-full bg-white rounded-2xl shadow-2xl mx-4 flex flex-col"
        style={{ maxWidth: 480 }}
      >
        {/* Header */}
        <div className="border-b border-gray-100 px-6 py-4 pr-12">
          <h2 className="text-lg font-bold text-gray-900">
            Run Ground-Truth Evaluation
          </h2>
        </div>

        {/* Close button */}
        {!running && (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 text-xl leading-none z-10"
          >
            ✕
          </button>
        )}

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {/* Client picker */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">
              Client
            </label>
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              disabled={running}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-200 disabled:opacity-50"
            >
              {EVAL_CLIENTS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Running hint */}
          {running && (
            <div className="flex items-center gap-3 rounded-lg bg-blue-50 px-4 py-3">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600 shrink-0" />
              <p className="text-xs text-blue-700">
                This takes ~1-2 minutes. Running all ground-truth questions against the RAG pipeline…
              </p>
            </div>
          )}

          {/* Error */}
          {runError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
              <p className="text-xs text-red-700">{runError}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-gray-100 px-6 py-4">
          <button
            onClick={onClose}
            disabled={running}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60"
          >
            {running && (
              <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            )}
            {running ? "Running eval…" : "Run"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function RagAnalyticsPage() {
  const token = process.env.NEXT_PUBLIC_ADMIN_TOKEN ?? null;
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [evals, setEvals] = useState<EvalListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Drill-down modal state
  const [selectedEvalId, setSelectedEvalId] = useState<string | null>(null);
  const [evalDetail, setEvalDetail] = useState<EvalDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Run eval modal state
  const [showRunModal, setShowRunModal] = useState(false);

  const refreshData = useCallback(async () => {
    if (!token) return;
    try {
      const [s, e] = await Promise.all([
        apiFetch<EvalSummary>(token, "/admin/rag-analytics/summary?days=30"),
        apiFetch<EvalListItem[]>(token, "/admin/rag-analytics/evaluations?limit=20"),
      ]);
      setSummary(s);
      setEvals(e);
    } catch {
      // Silently fail on refresh — page already has data
    }
  }, [token]);

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

  const openDetail = useCallback(
    async (evaluationId: string) => {
      setSelectedEvalId(evaluationId);
      setEvalDetail(null);
      setDetailError(null);
      setDetailLoading(true);
      try {
        const detail = await apiFetch<EvalDetail>(
          token,
          `/admin/rag-analytics/evaluations/${evaluationId}`,
        );
        setEvalDetail(detail);
      } catch (err) {
        setDetailError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setDetailLoading(false);
      }
    },
    [token],
  );

  const closeDetail = useCallback(() => {
    setSelectedEvalId(null);
    setEvalDetail(null);
    setDetailError(null);
  }, []);

  const handleEvalSuccess = useCallback(
    async (evalId: string, retrieval: number | null, keyword: number | null) => {
      // Close run modal
      setShowRunModal(false);

      // Toast (alert fallback)
      const msg = `Eval complete: ${fmtPct(retrieval)} retrieval, ${fmtPct(keyword)} keyword`;
      alert(msg);

      // Refresh data so new run appears
      await refreshData();

      // Auto-open drilldown for the new eval
      openDetail(evalId);
    },
    [refreshData, openDetail],
  );

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
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
              Admin
            </p>
            <h1 className="mt-1 text-2xl font-bold text-gray-900">
              RAG Analytics
            </h1>
          </div>
          <button
            onClick={() => setShowRunModal(true)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
          >
            Run Eval
          </button>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
          <p className="text-sm text-gray-500">
            No eval runs yet — click Run Eval to start
          </p>
        </div>

        {showRunModal && (
          <RunEvalModal
            token={token}
            onClose={() => setShowRunModal(false)}
            onSuccess={handleEvalSuccess}
          />
        )}
      </div>
    );
  }

  // ── Main render ───────────────────────────────────────────────────────

  const { latest_run } = summary;

  return (
    <div className="px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
            Admin
          </p>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">
            RAG Analytics
          </h1>
        </div>
        <button
          onClick={() => setShowRunModal(true)}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          Run Eval
        </button>
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
                    className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
                    onClick={() => openDetail(e.evaluation_id)}
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

      {/* Drill-down modal */}
      {selectedEvalId && (
        <EvalDetailModal
          detail={evalDetail}
          loading={detailLoading}
          error={detailError}
          onClose={closeDetail}
        />
      )}

      {/* Run eval modal */}
      {showRunModal && (
        <RunEvalModal
          token={token}
          onClose={() => setShowRunModal(false)}
          onSuccess={handleEvalSuccess}
        />
      )}
    </div>
  );
}
