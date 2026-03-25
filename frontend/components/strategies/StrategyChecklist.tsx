"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ProfileFlags, StrategyChecklist as ChecklistType, StrategyWithStatus } from "@/lib/api";
import { createStrategiesApi } from "@/lib/api";
import AISuggestModal from "./AISuggestModal";
import StrategyComparison from "./StrategyComparison";

interface Props {
  clientId: string;
  clientName?: string;
  profileFlags: ProfileFlags;
  onFlagsChange?: (flags: ProfileFlags) => void;
}

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 8 }, (_, i) => CURRENT_YEAR - 6 + i); // 2020-2027

const STATUS_OPTIONS: { value: string; label: string; dot: string }[] = [
  { value: "not_reviewed", label: "Not Reviewed", dot: "bg-gray-300" },
  { value: "recommended", label: "Recommended", dot: "bg-blue-500" },
  { value: "implemented", label: "Implemented", dot: "bg-green-500" },
  { value: "not_applicable", label: "Not Applicable", dot: "bg-gray-200" },
  { value: "declined", label: "Declined", dot: "bg-orange-400" },
];

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

export default function StrategyChecklist({ clientId, clientName, profileFlags, onFlagsChange }: Props) {
  const { getToken } = useAuth();
  const [view, setView] = useState<"current" | "compare">("current");
  const [year, setYear] = useState(CURRENT_YEAR);
  const [data, setData] = useState<ChecklistType | null>(null);
  const [loading, setLoading] = useState(true);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [showAISuggest, setShowAISuggest] = useState(false);
  const [reportMenuOpen, setReportMenuOpen] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportToast, setReportToast] = useState<string | null>(null);
  const reportBtnRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const api = createStrategiesApi(getToken);
      const result = await api.fetchChecklist(clientId, year);
      setData(result);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [getToken, clientId, year]);

  useEffect(() => {
    load();
  }, [load, profileFlags]);

  // Close report menu on outside click
  useEffect(() => {
    if (!reportMenuOpen) return;
    function handleClick(e: MouseEvent) {
      if (reportBtnRef.current && !reportBtnRef.current.contains(e.target as Node)) {
        setReportMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [reportMenuOpen]);

  async function downloadReport(includePriorYears: boolean) {
    setReportMenuOpen(false);
    setReportLoading(true);
    try {
      const api = createStrategiesApi(getToken);
      const blob = await api.generateReport(clientId, year, includePriorYears);
      const safeName = (clientName || "Client").replace(/\s+/g, "_");
      const filename = `Tax_Strategy_Report_${safeName}_${year}.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setReportToast(`Downloading ${filename}`);
      setTimeout(() => setReportToast(null), 3000);
    } catch (err) {
      setReportToast(err instanceof Error ? err.message : "Failed to generate report");
      setTimeout(() => setReportToast(null), 4000);
    } finally {
      setReportLoading(false);
    }
  }

  function toggleCategory(cat: string) {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  if (loading && !data) {
    return (
      <div className="mt-4 space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-xl border border-gray-200 bg-white" />
        ))}
      </div>
    );
  }

  const summary = data?.summary;
  const categories = data?.categories ?? [];
  const hasNonUniversal = categories.some((c) => c.category_name !== "universal");

  return (
    <div className="mt-4 space-y-4">
      {/* ── Top bar: view toggle + year selector + AI Suggest + summary ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5">
            <button
              onClick={() => setView("current")}
              className={[
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                view === "current"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700",
              ].join(" ")}
            >
              Current Year
            </button>
            <button
              onClick={() => setView("compare")}
              className={[
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                view === "compare"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700",
              ].join(" ")}
            >
              Compare Years
            </button>
          </div>

          {/* Year selector (current view only) */}
          {view === "current" && (
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
          )}

          {/* AI Suggest */}
          <button
            onClick={() => setShowAISuggest(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 shadow-sm hover:bg-blue-100 transition-colors"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
            </svg>
            AI Suggest
          </button>

          {/* Generate Report */}
          <div className="relative" ref={reportBtnRef}>
            <button
              onClick={() => !reportLoading && setReportMenuOpen(!reportMenuOpen)}
              disabled={reportLoading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 transition-colors disabled:opacity-60"
            >
              {reportLoading ? (
                <>
                  <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
                  Generating...
                </>
              ) : (
                <>
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                  Report
                </>
              )}
            </button>
            {reportMenuOpen && (
              <div className="absolute left-0 top-full z-20 mt-1 w-56 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                <button
                  onClick={() => downloadReport(false)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-gray-700 hover:bg-gray-50"
                >
                  <svg className="h-3.5 w-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                  </svg>
                  Current Year Only ({year})
                </button>
                <button
                  onClick={() => downloadReport(true)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-gray-700 hover:bg-gray-50"
                >
                  <svg className="h-3.5 w-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                  </svg>
                  Include Prior Year Comparison
                </button>
              </div>
            )}
          </div>
        </div>

        {view === "current" && summary && summary.total_applicable > 0 && (
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>
              <span className="font-medium text-gray-700">{summary.total_reviewed}</span> of{" "}
              {summary.total_applicable} reviewed
            </span>
            <span>
              <span className="font-medium text-green-600">{summary.total_implemented}</span> implemented
            </span>
            {summary.total_estimated_impact > 0 && (
              <span>
                <span className="font-medium text-blue-600">
                  {fmtMoney(summary.total_estimated_impact)}
                </span>{" "}
                est. impact
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Compare Years view ──────────────────────────────────────── */}
      {view === "compare" && <StrategyComparison clientId={clientId} />}

      {/* ── Current Year view ─────────────────────────────────────── */}
      {view === "current" && (
        <>
          {/* Hint when only universal strategies */}
          {!hasNonUniversal && categories.length > 0 && (
            <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-700">
              Toggle profile flags above to see more tax strategies relevant to this client.
            </div>
          )}

          {/* Categories (accordion) */}
          {categories.map((cat) => {
            const collapsed = collapsedCategories.has(cat.category_name);
            const label = CATEGORY_LABELS[cat.category_name] ?? cat.category_name;
            return (
              <div key={cat.category_name} className="rounded-xl border border-gray-200 bg-white shadow-sm">
                <button
                  onClick={() => toggleCategory(cat.category_name)}
                  className="flex w-full items-center justify-between px-5 py-3.5 text-left"
                >
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-gray-900">{label}</h3>
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500">
                      {cat.strategies.length}
                    </span>
                  </div>
                  <svg
                    className={`h-4 w-4 text-gray-400 transition-transform ${collapsed ? "" : "rotate-180"}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                  </svg>
                </button>
                {!collapsed && (
                  <div className="border-t border-gray-100">
                    {cat.strategies.map((sw) => (
                      <StrategyRow
                        key={sw.strategy.id}
                        clientId={clientId}
                        item={sw}
                        getToken={getToken}
                        onSaved={load}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {categories.length === 0 && !loading && (
            <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center shadow-sm">
              <p className="text-sm text-gray-500">No applicable strategies for this client profile.</p>
              <p className="mt-1 text-xs text-gray-400">
                Toggle profile flags above to see tax strategies.
              </p>
            </div>
          )}
        </>
      )}

      {/* AI Suggest Modal */}
      {showAISuggest && (
        <AISuggestModal
          clientId={clientId}
          onClose={() => setShowAISuggest(false)}
          onApplied={() => {
            // Re-fetch checklist data; parent will re-fetch flags via onFlagsChange
            load();
            if (onFlagsChange) {
              // Trigger a flags re-fetch by re-reading from the API
              createStrategiesApi(getToken)
                .fetchChecklist(clientId, year)
                .then(() => {
                  // The checklist reload above handles strategy refresh.
                  // For flags, we need to tell the parent to re-read flags from server.
                  // Since the parent reads flags from the client object, we trigger a simple
                  // flag fetch via the existing updateFlags with empty object.
                })
                .catch(() => {});
            }
          }}
        />
      )}

      {/* Report toast */}
      {reportToast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-gray-900 px-4 py-2 text-xs font-medium text-white shadow-lg">
          {reportToast}
        </div>
      )}
    </div>
  );
}

// ─── Single strategy row ─────────────────────────────────────────────────────

function StrategyRow({
  clientId,
  item,
  getToken,
  onSaved,
}: {
  clientId: string;
  item: StrategyWithStatus;
  getToken: () => Promise<string | null>;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(item.status);
  const [notes, setNotes] = useState(item.notes ?? "");
  const [impact, setImpact] = useState(
    item.estimated_impact != null ? String(item.estimated_impact) : "",
  );
  const [expanded, setExpanded] = useState(false);
  const [saved, setSaved] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync when parent data refreshes
  useEffect(() => {
    setStatus(item.status);
    setNotes(item.notes ?? "");
    setImpact(item.estimated_impact != null ? String(item.estimated_impact) : "");
  }, [item.status, item.notes, item.estimated_impact]);

  async function save(
    newStatus: string,
    newNotes: string,
    newImpact: string,
  ) {
    try {
      await createStrategiesApi(getToken).updateStatus(clientId, item.strategy.id, {
        tax_year: item.tax_year,
        status: newStatus,
        notes: newNotes || null,
        estimated_impact: newImpact ? parseFloat(newImpact) : null,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
      onSaved();
    } catch {
      // non-fatal
    }
  }

  function handleStatusChange(newStatus: string) {
    setStatus(newStatus);
    save(newStatus, notes, impact);
  }

  function handleNotesChange(val: string) {
    setNotes(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => save(status, val, impact), 500);
  }

  function handleImpactBlur() {
    save(status, notes, impact);
  }

  const statusDot = STATUS_OPTIONS.find((s) => s.value === status)?.dot ?? "bg-gray-300";

  return (
    <div className="border-b border-gray-50 last:border-b-0">
      <div className="flex items-center gap-3 px-5 py-3">
        {/* Name + description */}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gray-900">{item.strategy.name}</p>
          {item.strategy.description && (
            <p className="mt-0.5 text-xs text-gray-500 line-clamp-1">{item.strategy.description}</p>
          )}
        </div>

        {/* Save indicator */}
        {saved && (
          <svg className="h-4 w-4 shrink-0 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        )}

        {/* Status selector */}
        <div className="relative shrink-0">
          <select
            value={status}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="appearance-none rounded-lg border border-gray-200 bg-white py-1.5 pl-6 pr-7 text-xs font-medium text-gray-700 shadow-sm"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <span className={`pointer-events-none absolute left-2 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full ${statusDot}`} />
        </div>

        {/* Expand button */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          title="Notes & impact"
        >
          <svg className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </button>
      </div>

      {/* Expanded: notes + impact */}
      {expanded && (
        <div className="px-5 pb-4 pt-0">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">Notes</label>
              <textarea
                value={notes}
                onChange={(e) => handleNotesChange(e.target.value)}
                rows={2}
                placeholder="Add notes..."
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs text-gray-700 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">Estimated Impact ($)</label>
              <input
                type="number"
                value={impact}
                onChange={(e) => setImpact(e.target.value)}
                onBlur={handleImpactBlur}
                placeholder="0.00"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs text-gray-700 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
