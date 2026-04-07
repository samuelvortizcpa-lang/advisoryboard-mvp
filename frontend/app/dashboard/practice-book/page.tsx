"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import type { ClientHealthRow, PracticeSummary } from "@/lib/api";
import { createPracticeBookApi } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import SectionCard from "@/components/ui/SectionCard";

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}k`;
  return `$${n.toLocaleString()}`;
}

function healthColor(score: number): string {
  if (score >= 70) return "text-green-600";
  if (score >= 40) return "text-amber-600";
  return "text-red-600";
}

function healthBarColor(score: number): string {
  if (score >= 70) return "bg-green-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-red-500";
}

function healthTrackColor(score: number): string {
  if (score >= 70) return "bg-green-100";
  if (score >= 40) return "bg-amber-100";
  return "bg-red-100";
}

function healthBadgeBg(score: number): string {
  if (score >= 70) return "bg-green-50 text-green-700";
  if (score >= 40) return "bg-amber-50 text-amber-700";
  return "bg-red-50 text-red-700";
}

function formatDate(d: string | null): string {
  if (!d) return "Never";
  const date = new Date(d);
  if (isNaN(date.getTime())) return "—";
  const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

type SortKey = "name" | "entity_type" | "health_score" | "last_contact" | "open_action_count" | "document_count" | "estimated_impact";
type SortDir = "asc" | "desc";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function PracticeBookPage() {
  const { getToken } = useAuth();
  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("health_score");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [showExportMenu, setShowExportMenu] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const api = createPracticeBookApi(getToken);
      const data = await api.fetchSummary();
      setSummary(data);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    load();
  }, [load]);

  // Sort clients
  const sortedClients = [...(summary?.clients ?? [])].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return dir;
    if (bv == null) return -dir;
    if (typeof av === "string" && typeof bv === "string") return av.localeCompare(bv) * dir;
    return ((av as number) - (bv as number)) * dir;
  });

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "health_score" ? "asc" : "desc");
    }
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return null;
    return <span className="ml-0.5 text-[9px]">{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>;
  }

  async function handleExportPdf() {
    setExporting("pdf");
    try {
      const api = createPracticeBookApi(getToken);
      const blob = await api.exportPdf();
      downloadBlob(blob, "practice-book.pdf");
    } catch {
      // non-fatal
    } finally {
      setExporting(null);
    }
  }

  async function handleExportJson() {
    setExporting("json");
    setShowExportMenu(false);
    try {
      const api = createPracticeBookApi(getToken);
      const data = await api.exportJson();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      downloadBlob(blob, "practice-book.json");
    } catch {
      // non-fatal
    } finally {
      setExporting(null);
    }
  }

  async function handleExportCsv() {
    setExporting("csv");
    setShowExportMenu(false);
    try {
      const api = createPracticeBookApi(getToken);
      const blob = await api.exportCsv();
      downloadBlob(blob, "practice-book.csv");
    } catch {
      // non-fatal
    } finally {
      setExporting(null);
    }
  }

  async function handleExportSingleClient(clientId: string, clientName: string) {
    setExporting(clientId);
    try {
      const api = createPracticeBookApi(getToken);
      const blob = await api.exportSingleClientPdf(clientId);
      downloadBlob(blob, `practice-book-${clientName.toLowerCase().replace(/\s+/g, "-")}.pdf`);
    } catch {
      // non-fatal
    } finally {
      setExporting(null);
    }
  }

  // Transition readiness: attention items
  const attentionItems = (summary?.clients ?? []).reduce<
    { type: string; client_id: string; name: string; detail: string }[]
  >((acc, c) => {
    if (c.health_score < 40)
      acc.push({ type: "low_health", client_id: c.client_id, name: c.name, detail: `Health score: ${c.health_score}` });
    if (c.journal_count === 0)
      acc.push({ type: "no_journal", client_id: c.client_id, name: c.name, detail: "No journal entries" });
    if (c.health_breakdown?.breakdown?.documents === 0)
      acc.push({ type: "no_returns", client_id: c.client_id, name: c.name, detail: "Missing recent year returns" });
    if (c.communication_count === 0)
      acc.push({ type: "no_comms", client_id: c.client_id, name: c.name, detail: "No communications in past year" });
    return acc;
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Practice Book</h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Engagement health and transition readiness across your practice
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Export Data dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu((v) => !v)}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              <DownloadIcon />
              Export Data
              <ChevronDownIcon />
            </button>
            {showExportMenu && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowExportMenu(false)} />
                <div className="absolute right-0 z-20 mt-1 w-40 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                  <button
                    onClick={handleExportJson}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <CodeIcon />
                    JSON Export
                  </button>
                  <button
                    onClick={handleExportCsv}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <TableIcon />
                    CSV Summary
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Export Full Practice Book (PDF) */}
          <button
            onClick={handleExportPdf}
            disabled={exporting !== null}
            className="flex items-center gap-1.5 rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-gray-800 disabled:opacity-50"
          >
            {exporting === "pdf" ? <SmallSpinner /> : <BookIcon />}
            Export Full Practice Book
          </button>
        </div>
      </div>

      {/* ── Loading skeleton ──────────────────────────────────────────── */}
      {loading && !summary && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      )}

      {/* ── Stat cards ────────────────────────────────────────────────── */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Total Clients"
            value={summary.total_clients}
            context={Object.entries(summary.by_entity_type)
              .slice(0, 2)
              .map(([k, v]) => `${v} ${k}`)
              .join(", ")}
            contextType="muted"
          />
          <div className="group relative rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
            <p className="text-xs text-gray-500">Avg. Engagement Health</p>
            <p className={`mt-1 text-3xl font-bold ${healthColor(summary.avg_engagement_health)}`}>
              {summary.avg_engagement_health}
            </p>
            <p className="mt-1 text-xs text-gray-400">
              {summary.avg_engagement_health >= 70 ? "Healthy practice" : summary.avg_engagement_health >= 40 ? "Needs improvement" : "Requires attention"}
            </p>
          </div>
          <StatCard
            label="Transition Readiness"
            value={`${summary.transition_readiness}%`}
            context={`${summary.clients.filter((c) => c.health_score > 60).length} of ${summary.total_clients} clients ready`}
            contextType={summary.transition_readiness >= 70 ? "success" : summary.transition_readiness >= 40 ? "warning" : "danger"}
          />
          <StatCard
            label="Advisory Impact"
            value={fmtMoney(summary.total_advisory_impact)}
            context="total implemented savings"
            contextType="success"
          />
        </div>
      )}

      {/* ── Client Health Table ────────────────────────────────────────── */}
      <SectionCard title="Client Health">
        {sortedClients.length === 0 && !loading ? (
          <p className="py-6 text-center text-xs text-gray-400">No clients found</p>
        ) : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100 text-left text-gray-500">
                  <SortHeader label="Client" sortKey="name" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} />
                  <SortHeader label="Entity Type" sortKey="entity_type" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} />
                  <SortHeader label="Health Score" sortKey="health_score" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} wide />
                  <SortHeader label="Last Contact" sortKey="last_contact" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} />
                  <SortHeader label="Open Items" sortKey="open_action_count" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} right />
                  <SortHeader label="Docs" sortKey="document_count" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} right />
                  <SortHeader label="Impact" sortKey="estimated_impact" currentKey={sortKey} onClick={toggleSort} indicator={sortIndicator} right />
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {sortedClients.map((c) => (
                  <tr
                    key={c.client_id}
                    className="border-b border-gray-50 last:border-b-0 hover:bg-gray-50"
                  >
                    <td className="px-5 py-2.5">
                      <Link
                        href={`/dashboard/clients/${c.client_id}`}
                        className="font-medium text-gray-900 hover:text-blue-600"
                      >
                        {c.name}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">
                        {c.entity_type}
                      </span>
                    </td>
                    <td className="px-3 py-2.5" style={{ minWidth: 140 }}>
                      <div className="flex items-center gap-2">
                        <span className={`w-6 text-right text-[11px] font-semibold ${healthColor(c.health_score)}`}>
                          {c.health_score}
                        </span>
                        <div className={`h-1.5 flex-1 rounded-full ${healthTrackColor(c.health_score)}`}>
                          <div
                            className={`h-1.5 rounded-full ${healthBarColor(c.health_score)} transition-all`}
                            style={{ width: `${Math.max(c.health_score, 2)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-gray-600">
                      {formatDate(c.last_contact)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {c.open_action_count > 0 ? (
                        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${healthBadgeBg(c.open_action_count <= 2 ? 70 : c.open_action_count <= 5 ? 50 : 20)}`}>
                          {c.open_action_count}
                        </span>
                      ) : (
                        <span className="text-gray-400">0</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-gray-700">
                      {c.document_count}
                    </td>
                    <td className="px-3 py-2.5 text-right text-gray-700">
                      {c.estimated_impact > 0 ? fmtMoney(c.estimated_impact) : "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        onClick={() => handleExportSingleClient(c.client_id, c.name)}
                        disabled={exporting !== null}
                        title="Export client PDF"
                        className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-40"
                      >
                        {exporting === c.client_id ? <SmallSpinner /> : <DownloadSmallIcon />}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {/* ── Transition Readiness ──────────────────────────────────────── */}
      {summary && (
        <SectionCard title="Transition Readiness">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
            {/* Progress ring */}
            <div className="flex flex-col items-center gap-2">
              <div className="relative h-28 w-28">
                <svg className="h-28 w-28 -rotate-90" viewBox="0 0 112 112">
                  <circle cx="56" cy="56" r="48" fill="none" stroke="#f3f4f6" strokeWidth="8" />
                  <circle
                    cx="56"
                    cy="56"
                    r="48"
                    fill="none"
                    stroke={summary.transition_readiness >= 70 ? "#22c55e" : summary.transition_readiness >= 40 ? "#f59e0b" : "#ef4444"}
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${(summary.transition_readiness / 100) * 301.6} 301.6`}
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-2xl font-bold ${healthColor(summary.transition_readiness)}`}>
                    {summary.transition_readiness}%
                  </span>
                  <span className="text-[10px] text-gray-400">ready</span>
                </div>
              </div>
            </div>

            {/* Attention items */}
            <div className="flex-1">
              {attentionItems.length === 0 ? (
                <div className="flex items-center gap-2 rounded-lg border border-green-100 bg-green-50 p-3">
                  <CheckCircleIcon />
                  <p className="text-xs font-medium text-green-700">
                    All clients meet readiness thresholds
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-gray-700">
                    Attention needed ({attentionItems.length} item{attentionItems.length !== 1 ? "s" : ""})
                  </p>
                  <div className="max-h-64 space-y-1 overflow-y-auto">
                    {attentionItems.map((item, i) => (
                      <Link
                        key={`${item.client_id}-${item.type}-${i}`}
                        href={`/dashboard/clients/${item.client_id}`}
                        className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-50"
                      >
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${item.type === "low_health" ? "bg-red-400" : "bg-amber-400"}`} />
                        <span className="font-medium text-gray-900">{item.name}</span>
                        <span className="text-gray-400">—</span>
                        <span>{item.detail}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </SectionCard>
      )}
    </div>
  );
}

// ─── Sort header component ──────────────────────────────────────────────────

function SortHeader({
  label,
  sortKey,
  currentKey,
  onClick,
  indicator,
  right,
  wide,
}: {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey;
  onClick: (key: SortKey) => void;
  indicator: (key: SortKey) => React.ReactNode;
  right?: boolean;
  wide?: boolean;
}) {
  return (
    <th
      className={`cursor-pointer select-none px-3 py-2 font-medium transition-colors hover:text-gray-700 ${sortKey === "name" ? "px-5" : ""} ${right ? "text-right" : ""}`}
      style={wide ? { minWidth: 140 } : undefined}
      onClick={() => onClick(sortKey)}
    >
      {label}
      {currentKey === sortKey && indicator(sortKey)}
    </th>
  );
}

// ─── Icons ──────────────────────────────────────────────────────────────────

function BookIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  );
}

function DownloadSmallIcon() {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  );
}

function CodeIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M10.875 12h-7.5c-.621 0-1.125.504-1.125 1.125M10.875 12c-.621 0-1.125.504-1.125 1.125M10.875 12c.621 0 1.125.504 1.125 1.125m1.125 0c.621 0 1.125.504 1.125 1.125M13.125 12h7.5c.621 0 1.125.504 1.125 1.125m-9.75 0v-1.5m0 1.5c0 .621.504 1.125 1.125 1.125m-1.125-1.125c0 .621-.504 1.125-1.125 1.125" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg className="h-4 w-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function SmallSpinner() {
  return (
    <span className="block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-transparent" />
  );
}
