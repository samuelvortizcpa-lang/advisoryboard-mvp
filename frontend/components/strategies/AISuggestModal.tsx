"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import type { AISuggestResponse, StrategySuggestion } from "@/lib/api";
import { createStrategiesApi } from "@/lib/api";

interface Props {
  clientId: string;
  onClose: () => void;
  onApplied: () => void;
}

const STATUS_OPTIONS: { value: string; label: string; dot: string }[] = [
  { value: "not_reviewed", label: "Not Reviewed", dot: "bg-gray-300" },
  { value: "recommended", label: "Recommended", dot: "bg-blue-500" },
  { value: "implemented", label: "Implemented", dot: "bg-green-500" },
  { value: "not_applicable", label: "Not Applicable", dot: "bg-gray-200" },
  { value: "declined", label: "Declined", dot: "bg-orange-400" },
];

const FLAG_LABELS: Record<string, string> = {
  has_business_entity: "Business Entity",
  has_real_estate: "Real Estate",
  is_real_estate_professional: "RE Professional",
  has_high_income: "High Income",
  has_estate_planning: "Estate Planning",
  is_medical_professional: "Medical Professional",
  has_retirement_plans: "Retirement Plans",
  has_investments: "Investments",
  has_employees: "Employees",
};

const PROGRESS_MESSAGES = [
  "Reading tax returns...",
  "Identifying strategies...",
  "Generating recommendations...",
];

type Phase = "loading" | "review" | "applying" | "error" | "empty";

export default function AISuggestModal({ clientId, onClose, onApplied }: Props) {
  const { getToken } = useAuth();
  const [phase, setPhase] = useState<Phase>("loading");
  const [progressIdx, setProgressIdx] = useState(0);
  const [data, setData] = useState<AISuggestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Selection state
  const [selectedFlags, setSelectedFlags] = useState<Set<number>>(new Set());
  const [selectedStrategies, setSelectedStrategies] = useState<Set<number>>(new Set());
  const [strategyOverrides, setStrategyOverrides] = useState<Record<number, string>>({});

  // Toast
  const [toast, setToast] = useState<string | null>(null);

  // Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Progress cycling during loading
  useEffect(() => {
    if (phase !== "loading") return;
    const interval = setInterval(() => {
      setProgressIdx((prev) => (prev + 1) % PROGRESS_MESSAGES.length);
    }, 2000);
    return () => clearInterval(interval);
  }, [phase]);

  // Fetch suggestions on mount
  const fetchSuggestions = useCallback(async () => {
    setPhase("loading");
    setProgressIdx(0);
    setError(null);
    try {
      const api = createStrategiesApi(getToken);
      const result = await api.aiSuggestStrategies(clientId);
      setData(result);

      if (
        result.documents_analyzed === 0 &&
        result.flag_suggestions.length === 0 &&
        result.strategy_suggestions.length === 0
      ) {
        setPhase("empty");
        return;
      }

      // Default selections: all flags checked, strategies checked if implemented/recommended
      setSelectedFlags(new Set(result.flag_suggestions.map((_, i) => i)));
      const defaultStrategies = new Set<number>();
      result.strategy_suggestions.forEach((s, i) => {
        if (s.suggested_status === "implemented" || s.suggested_status === "recommended") {
          defaultStrategies.add(i);
        }
      });
      setSelectedStrategies(defaultStrategies);
      setStrategyOverrides({});
      setPhase("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate suggestions");
      setPhase("error");
    }
  }, [getToken, clientId]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  // Apply selected suggestions
  async function handleApply() {
    if (!data) return;
    setPhase("applying");

    const acceptedFlags = data.flag_suggestions
      .filter((_, i) => selectedFlags.has(i))
      .map((f) => ({ flag: f.flag, value: f.suggested_value }));

    const acceptedStrategies = data.strategy_suggestions
      .filter((_, i) => selectedStrategies.has(i))
      .filter((s) => s.strategy_id)
      .map((s) => {
        const realIdx = data.strategy_suggestions.indexOf(s);
        return {
          strategy_id: s.strategy_id!,
          status: strategyOverrides[realIdx] ?? s.suggested_status,
          notes: `AI suggested: ${s.reason}`,
        };
      });

    try {
      const api = createStrategiesApi(getToken);
      const result = await api.applySuggestions(clientId, {
        accepted_flags: acceptedFlags,
        accepted_strategies: acceptedStrategies,
        tax_year: data.tax_year,
      });
      setToast(`Applied ${result.flags_updated} flag updates and ${result.strategies_updated} strategy suggestions`);
      setTimeout(() => {
        onApplied();
        onClose();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply suggestions");
      setPhase("review");
    }
  }

  // Counts
  const flagCount = selectedFlags.size;
  const stratCount = selectedStrategies.size;

  function statusCounts(suggestions: StrategySuggestion[]) {
    const counts: Record<string, number> = {};
    suggestions.forEach((s) => {
      counts[s.suggested_status] = (counts[s.suggested_status] || 0) + 1;
    });
    return counts;
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30 transition-opacity" onClick={onClose} />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-white shadow-2xl animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div className="flex items-center gap-2">
            <svg className="h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
            </svg>
            <h2 className="text-base font-semibold text-gray-900">AI Strategy Suggestions</h2>
          </div>
          <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {/* Loading */}
          {phase === "loading" && (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
              <p className="mt-4 text-sm font-medium text-gray-700">
                Analyzing documents...
              </p>
              <p className="mt-1 text-xs text-gray-500">{PROGRESS_MESSAGES[progressIdx]}</p>
            </div>
          )}

          {/* Applying */}
          {phase === "applying" && (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
              <p className="mt-4 text-sm font-medium text-gray-700">Applying suggestions...</p>
            </div>
          )}

          {/* Empty state */}
          {phase === "empty" && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <svg className="h-12 w-12 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
              <p className="mt-4 text-sm font-medium text-gray-700">
                Upload documents first to enable AI suggestions
              </p>
              <p className="mt-1 max-w-xs text-xs text-gray-500">
                The AI analyzes tax returns and financial documents to recommend strategies.
              </p>
              <button
                onClick={onClose}
                className="mt-6 rounded-lg border border-gray-200 bg-white px-4 py-2 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50"
              >
                Close
              </button>
            </div>
          )}

          {/* Error state */}
          {phase === "error" && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <svg className="h-12 w-12 text-red-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              <p className="mt-4 text-sm font-medium text-gray-700">Something went wrong</p>
              <p className="mt-1 max-w-xs text-xs text-gray-500">{error}</p>
              <button
                onClick={fetchSuggestions}
                className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-blue-700"
              >
                Try Again
              </button>
            </div>
          )}

          {/* Review */}
          {phase === "review" && data && (
            <div className="space-y-6">
              {/* Summary counts */}
              {data.strategy_suggestions.length > 0 && (
                <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-700">
                  AI analyzed {data.documents_analyzed} document{data.documents_analyzed !== 1 ? "s" : ""} and suggests{" "}
                  {(() => {
                    const counts = statusCounts(data.strategy_suggestions);
                    const parts: string[] = [];
                    if (counts.implemented) parts.push(`${counts.implemented} implemented`);
                    if (counts.recommended) parts.push(`${counts.recommended} recommended`);
                    if (counts.not_applicable) parts.push(`${counts.not_applicable} not applicable`);
                    if (counts.not_reviewed) parts.push(`${counts.not_reviewed} not reviewed`);
                    return parts.join(", ");
                  })()}
                </div>
              )}

              {/* Profile Flag Suggestions */}
              {data.flag_suggestions.length > 0 && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-gray-900">Profile Flag Suggestions</h3>
                  <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
                    {data.flag_suggestions.map((f, i) => (
                      <label
                        key={i}
                        className="flex items-start gap-3 border-b border-gray-50 px-4 py-3 last:border-b-0 cursor-pointer hover:bg-gray-50"
                      >
                        <input
                          type="checkbox"
                          checked={selectedFlags.has(i)}
                          onChange={() => {
                            setSelectedFlags((prev) => {
                              const next = new Set(prev);
                              if (next.has(i)) next.delete(i);
                              else next.add(i);
                              return next;
                            });
                          }}
                          className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-900">
                              {FLAG_LABELS[f.flag] ?? f.flag}
                            </span>
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                              f.suggested_value
                                ? "bg-green-100 text-green-700"
                                : "bg-gray-100 text-gray-600"
                            }`}>
                              {f.suggested_value ? "ON" : "OFF"}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs italic text-gray-500">{f.reason}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Strategy Suggestions */}
              {data.strategy_suggestions.length > 0 && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-gray-900">Strategy Suggestions</h3>
                  <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
                    {data.strategy_suggestions.map((s, i) => {
                      const effectiveStatus = strategyOverrides[i] ?? s.suggested_status;
                      const dotColor = STATUS_OPTIONS.find((o) => o.value === effectiveStatus)?.dot ?? "bg-gray-300";
                      return (
                        <label
                          key={i}
                          className="flex items-start gap-3 border-b border-gray-50 px-4 py-3 last:border-b-0 cursor-pointer hover:bg-gray-50"
                        >
                          <input
                            type="checkbox"
                            checked={selectedStrategies.has(i)}
                            onChange={() => {
                              setSelectedStrategies((prev) => {
                                const next = new Set(prev);
                                if (next.has(i)) next.delete(i);
                                else next.add(i);
                                return next;
                              });
                            }}
                            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-900">{s.strategy_name}</span>
                              {!s.strategy_id && (
                                <span className="rounded-full bg-yellow-100 px-1.5 py-0.5 text-[10px] text-yellow-700">
                                  unmatched
                                </span>
                              )}
                            </div>
                            <p className="mt-0.5 text-xs italic text-gray-500">{s.reason}</p>
                          </div>
                          {/* Status dropdown */}
                          <div className="relative shrink-0">
                            <select
                              value={effectiveStatus}
                              onChange={(e) => {
                                e.stopPropagation();
                                setStrategyOverrides((prev) => ({
                                  ...prev,
                                  [i]: e.target.value,
                                }));
                              }}
                              onClick={(e) => e.stopPropagation()}
                              className="appearance-none rounded-lg border border-gray-200 bg-white py-1.5 pl-6 pr-7 text-xs font-medium text-gray-700 shadow-sm"
                            >
                              {STATUS_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                            <span className={`pointer-events-none absolute left-2 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full ${dotColor}`} />
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {phase === "review" && data && (
          <div className="border-t border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-500">
                Apply {flagCount} flag change{flagCount !== 1 ? "s" : ""} and {stratCount} strategy update{stratCount !== 1 ? "s" : ""}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={onClose}
                  className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApply}
                  disabled={flagCount === 0 && stratCount === 0}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Apply Selected
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Toast */}
        {toast && (
          <div className="absolute bottom-20 left-1/2 -translate-x-1/2 rounded-lg bg-gray-900 px-4 py-2 text-xs font-medium text-white shadow-lg">
            {toast}
          </div>
        )}
      </div>
    </>
  );
}
