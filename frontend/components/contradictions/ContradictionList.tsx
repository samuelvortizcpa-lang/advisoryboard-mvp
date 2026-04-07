"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useOrg } from "@/contexts/OrgContext";
import {
  DataContradiction,
  ContradictionListResponse,
  createContradictionsApi,
} from "@/lib/api";
import ResolveModal from "./ResolveModal";

type StatusTab = "open" | "resolved" | "dismissed";

interface Props {
  clientId: string;
  onCountChange?: (openCount: number, highSeverity: boolean) => void;
}

export default function ContradictionList({ clientId, onCountChange }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.id;

  const [items, setItems] = useState<DataContradiction[]>([]);
  const [total, setTotal] = useState(0);
  const [openCount, setOpenCount] = useState(0);
  const [filter, setFilter] = useState<StatusTab>("open");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [resolveTarget, setResolveTarget] = useState<DataContradiction | null>(null);
  const [dismissConfirm, setDismissConfirm] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const api = createContradictionsApi(getToken, orgId);
  const perPage = 20;

  useEffect(() => {
    fetchItems(filter, 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, filter]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  async function fetchItems(tab: StatusTab = filter, p: number = page) {
    setLoading(true);
    setError(null);
    try {
      const res: ContradictionListResponse = await api.list(clientId, {
        status: tab,
        page: p,
        per_page: perPage,
      });
      setItems(res.contradictions);
      setTotal(res.total);
      setOpenCount(res.open_count);
      setPage(p);

      const hasHigh = res.contradictions.some((c) => c.severity === "high");
      onCountChange?.(res.open_count, hasHigh);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contradictions");
    } finally {
      setLoading(false);
    }
  }

  async function handleScan() {
    setScanning(true);
    try {
      const result = await api.scan(clientId);
      if (result.new_contradictions > 0) {
        setToast(`Found ${result.new_contradictions} new conflict${result.new_contradictions !== 1 ? "s" : ""}`);
        setFilter("open");
        await fetchItems("open", 1);
      } else {
        setToast("No new conflicts found");
      }
    } catch {
      setToast("Scan failed");
    } finally {
      setScanning(false);
    }
  }

  async function handleResolve(note: string) {
    if (!resolveTarget) return;
    try {
      await api.update(clientId, resolveTarget.id, {
        status: "resolved",
        resolution_note: note,
      });
      setResolveTarget(null);
      setToast("Contradiction resolved");
      await fetchItems(filter, page);
    } catch {
      setToast("Failed to resolve");
    }
  }

  async function handleDismiss(id: string) {
    try {
      await api.update(clientId, id, { status: "dismissed" });
      setDismissConfirm(null);
      setToast("Contradiction dismissed");
      await fetchItems(filter, page);
    } catch {
      setToast("Failed to dismiss");
    }
  }

  function handleTabChange(tab: StatusTab) {
    setFilter(tab);
    setPage(1);
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="relative">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-gray-900">Data Quality</h2>
          {openCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
              {openCount} open
            </span>
          )}
        </div>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
        >
          {scanning ? (
            <>
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-gray-500 border-t-transparent" />
              Scanning...
            </>
          ) : (
            <>
              <ScanIcon />
              Scan for conflicts
            </>
          )}
        </button>
      </div>

      {/* Filter tabs */}
      <div className="mb-3 flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 text-sm">
        {(["open", "resolved", "dismissed"] as StatusTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => handleTabChange(tab)}
            className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
              filter === tab
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
          <span>{error}</span>
          <button onClick={() => fetchItems(filter, page)} className="text-xs text-red-500 underline">
            Retry
          </button>
        </div>
      )}

      {/* Content */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
              <ShieldCheckIcon />
            </div>
            <p className="text-sm font-medium text-gray-700">
              {filter === "open" ? "No open contradictions" : `No ${filter} contradictions`}
            </p>
            <p className="mt-1 max-w-xs text-xs text-gray-400">
              {filter === "open"
                ? "All data sources are consistent. Use \"Scan for conflicts\" to check again."
                : `No contradictions have been ${filter} yet.`}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {items.map((item) => (
              <li key={item.id} className="px-4 py-3.5">
                <div className="flex items-start gap-3">
                  {/* Severity dot */}
                  <div className="mt-1 flex-shrink-0">
                    <span
                      className={`inline-block h-2.5 w-2.5 rounded-full ${
                        item.severity === "high"
                          ? "bg-red-500"
                          : item.severity === "medium"
                          ? "bg-yellow-500"
                          : "bg-gray-400"
                      }`}
                    />
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-800">{item.title}</p>

                    {/* Source labels */}
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {item.source_a_label && (
                        <span className="rounded-full bg-blue-50 border border-blue-100 px-2 py-0.5 text-[10px] text-blue-600">
                          {item.source_a_label}
                        </span>
                      )}
                      {item.source_b_label && (
                        <span className="rounded-full bg-purple-50 border border-purple-100 px-2 py-0.5 text-[10px] text-purple-600">
                          {item.source_b_label}
                        </span>
                      )}
                      {item.tax_year && (
                        <span className="rounded-full bg-gray-100 border border-gray-200 px-2 py-0.5 text-[10px] text-gray-600">
                          {item.tax_year}
                        </span>
                      )}
                    </div>

                    {/* Meta row */}
                    <div className="mt-1.5 flex items-center gap-3 text-[11px] text-gray-400">
                      <span className={`font-medium ${
                        item.severity === "high" ? "text-red-500" : item.severity === "medium" ? "text-yellow-600" : "text-gray-500"
                      }`}>
                        {item.severity}
                      </span>
                      <span>{item.contradiction_type.replace("_", " ")}</span>
                      <span>{formatRelativeTime(item.created_at)}</span>
                    </div>

                    {/* Resolution note (for resolved/dismissed tabs) */}
                    {item.status === "resolved" && item.resolution_note && (
                      <p className="mt-2 rounded-md bg-green-50 border border-green-100 px-2.5 py-1.5 text-xs text-green-700">
                        {item.resolution_note}
                      </p>
                    )}

                    {/* Actions (open tab only) */}
                    {item.status === "open" && (
                      <div className="mt-2 flex items-center gap-3">
                        <button
                          onClick={() => setResolveTarget(item)}
                          className="rounded-md bg-teal-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-teal-700"
                        >
                          Resolve
                        </button>
                        {dismissConfirm === item.id ? (
                          <span className="flex items-center gap-1.5 text-xs">
                            <span className="text-gray-500">Dismiss?</span>
                            <button
                              onClick={() => handleDismiss(item.id)}
                              className="font-medium text-red-600 hover:text-red-700"
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setDismissConfirm(null)}
                              className="text-gray-400 hover:text-gray-600"
                            >
                              No
                            </button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setDismissConfirm(item.id)}
                            className="text-xs text-gray-400 transition-colors hover:text-gray-600"
                          >
                            Dismiss
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            onClick={() => { setPage(page - 1); fetchItems(filter, page - 1); }}
            disabled={page <= 1 || loading}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-xs text-gray-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => { setPage(page + 1); fetchItems(filter, page + 1); }}
            disabled={page >= totalPages || loading}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {/* Resolve modal */}
      {resolveTarget && (
        <ResolveModal
          title={resolveTarget.title}
          description={resolveTarget.description}
          onResolve={handleResolve}
          onClose={() => setResolveTarget(null)}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ── Icons ────────────────────────────────────────────────────────────────────

function ScanIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

function ShieldCheckIcon() {
  return (
    <svg className="h-6 w-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  );
}
