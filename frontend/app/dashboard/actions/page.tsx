"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ActionItem, createActionItemsApi, createClientsApi } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type EnrichedActionItem = ActionItem & {
  clientName: string;
  clientTypeColor: string | null;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const COLOR_DOT: Record<string, string> = {
  blue: "bg-blue-500",
  green: "bg-green-500",
  purple: "bg-purple-500",
  red: "bg-red-500",
  gray: "bg-gray-400",
};

const PRIORITY_BADGE: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-gray-100 text-gray-600",
};

function isOverdue(item: EnrichedActionItem): boolean {
  if (!item.due_date || item.status !== "pending") return false;
  return new Date(item.due_date) < new Date(new Date().toDateString());
}

function formatDueDate(iso: string | null): { label: string; className: string } {
  if (!iso) return { label: "—", className: "text-gray-300" };
  const due = new Date(iso);
  const today = new Date(new Date().toDateString());
  const diffDays = Math.round((due.getTime() - today.getTime()) / 86_400_000);

  if (diffDays < 0) {
    return {
      label: `${Math.abs(diffDays)}d overdue`,
      className: "text-red-600 font-medium",
    };
  }
  if (diffDays === 0) return { label: "Today", className: "text-amber-600 font-medium" };
  if (diffDays === 1) return { label: "Tomorrow", className: "text-gray-700" };
  return {
    label: due.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }),
    className: "text-gray-600",
  };
}

// Sort: ascending due_date (overdue first), null due_dates last
function sortItems(items: EnrichedActionItem[]): EnrichedActionItem[] {
  return [...items].sort((a, b) => {
    if (!a.due_date && !b.due_date) return 0;
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
  });
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ActionsPage() {
  const { getToken } = useAuth();

  const [items, setItems] = useState<EnrichedActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<"pending" | "completed" | "all">(
    "pending"
  );
  const [priorityFilter, setPriorityFilter] = useState<"all" | "high" | "medium" | "low">(
    "all"
  );

  // IDs currently being marked complete
  const [completing, setCompleting] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const clientsApi = createClientsApi(getToken);
    const actionItemsApi = createActionItemsApi(getToken);

    clientsApi
      .list(0, 200)
      .then(async (clientsResp) => {
        const clients = clientsResp.items;

        // Fetch all action items per client in parallel; tolerate individual failures
        const results = await Promise.allSettled(
          clients.map((client) =>
            actionItemsApi.list(client.id, undefined, 0, 200).then((resp) =>
              resp.items.map(
                (item): EnrichedActionItem => ({
                  ...item,
                  clientName: client.name,
                  clientTypeColor: client.client_type?.color ?? null,
                })
              )
            )
          )
        );

        if (cancelled) return;

        const enriched: EnrichedActionItem[] = [];
        for (const r of results) {
          if (r.status === "fulfilled") enriched.push(...r.value);
        }

        setItems(sortItems(enriched));
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [getToken]);

  async function handleComplete(item: EnrichedActionItem) {
    setCompleting((prev) => new Set(prev).add(item.id));
    try {
      await createActionItemsApi(getToken).update(item.id, { status: "completed" });
      // Optimistic update: mark completed in local state
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, status: "completed" } : i))
      );
    } catch {
      // Leave item as-is if the PATCH fails
    } finally {
      setCompleting((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  }

  // Client-side filter
  const filtered = items.filter((item) => {
    if (statusFilter !== "all" && item.status !== statusFilter) return false;
    if (priorityFilter !== "all" && item.priority !== priorityFilter) return false;
    return true;
  });

  const pendingCount = items.filter((i) => i.status === "pending").length;
  const overdueCount = items.filter((i) => isOverdue(i)).length;

  return (
    <div className="px-8 py-8">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Action Items</h1>
          {!loading && (
            <p className="mt-0.5 text-sm text-gray-500">
              {pendingCount} pending
              {overdueCount > 0 && (
                <span className="ml-2 font-medium text-red-600">
                  · {overdueCount} overdue
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap gap-3">
        {/* Status toggle group */}
        <div className="flex overflow-hidden rounded-md border border-gray-200 bg-white">
          {(["pending", "all", "completed"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={[
                "px-3 py-1.5 text-xs font-medium capitalize transition-colors",
                statusFilter === s
                  ? "bg-blue-600 text-white"
                  : "text-gray-500 hover:bg-gray-50",
              ].join(" ")}
            >
              {s === "all" ? "All Statuses" : s}
            </button>
          ))}
        </div>

        {/* Priority toggle group */}
        <div className="flex overflow-hidden rounded-md border border-gray-200 bg-white">
          {(["all", "high", "medium", "low"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPriorityFilter(p)}
              className={[
                "px-3 py-1.5 text-xs font-medium capitalize transition-colors",
                priorityFilter === p
                  ? "bg-blue-600 text-white"
                  : "text-gray-500 hover:bg-gray-50",
              ].join(" ")}
            >
              {p === "all" ? "All Priorities" : p}
            </button>
          ))}
        </div>
      </div>

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Loading ──────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      )}

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {!loading && !error && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white py-20 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
            <CircleCheckIcon />
          </div>
          <p className="text-sm font-medium text-gray-900">
            {items.length === 0 ? "No action items yet" : "No items match your filters"}
          </p>
          <p className="mt-1 text-xs text-gray-400">
            {items.length === 0
              ? "Action items are extracted automatically from uploaded documents"
              : "Try adjusting your status or priority filters"}
          </p>
        </div>
      )}

      {/* ── Table ────────────────────────────────────────────────────────── */}
      {!loading && !error && filtered.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60">
                {["Task", "Client", "Priority", "Due Date", "Status", ""].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-400"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((item) => {
                const overdue = isOverdue(item);
                const dueInfo = formatDueDate(item.due_date);
                const isCompleting = completing.has(item.id);

                return (
                  <tr key={item.id} className="group transition-colors hover:bg-gray-50">
                    {/* Task — left-border accent when overdue */}
                    <td
                      className={[
                        "max-w-xs px-4 py-3.5",
                        overdue ? "border-l-2 border-l-red-400" : "",
                      ].join(" ")}
                    >
                      <p
                        className={[
                          "text-sm",
                          item.status === "completed"
                            ? "text-gray-400 line-through"
                            : "text-gray-900",
                        ].join(" ")}
                      >
                        {item.text}
                      </p>
                      {item.document_filename && (
                        <p className="mt-0.5 truncate text-xs text-gray-400">
                          {item.document_filename}
                        </p>
                      )}
                    </td>

                    {/* Client */}
                    <td className="px-4 py-3.5">
                      <Link
                        href={`/dashboard/clients/${item.client_id}?tab=actions`}
                        className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
                      >
                        {item.clientTypeColor && (
                          <span
                            className={[
                              "inline-block h-2 w-2 shrink-0 rounded-full",
                              COLOR_DOT[item.clientTypeColor] ?? "bg-gray-300",
                            ].join(" ")}
                          />
                        )}
                        {item.clientName}
                      </Link>
                    </td>

                    {/* Priority */}
                    <td className="px-4 py-3.5">
                      {item.priority ? (
                        <span
                          className={[
                            "inline-block rounded px-2 py-0.5 text-xs font-medium capitalize",
                            PRIORITY_BADGE[item.priority] ?? "bg-gray-100 text-gray-600",
                          ].join(" ")}
                        >
                          {item.priority}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-300">—</span>
                      )}
                    </td>

                    {/* Due Date */}
                    <td className={["px-4 py-3.5 text-sm", dueInfo.className].join(" ")}>
                      {dueInfo.label}
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3.5">
                      <span
                        className={[
                          "inline-block rounded px-2 py-0.5 text-xs font-medium capitalize",
                          item.status === "completed"
                            ? "bg-green-50 text-green-700"
                            : item.status === "cancelled"
                            ? "bg-gray-100 text-gray-500"
                            : overdue
                            ? "bg-red-50 text-red-700"
                            : "bg-blue-50 text-blue-700",
                        ].join(" ")}
                      >
                        {item.status === "pending" && overdue ? "overdue" : item.status}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3.5">
                      {item.status === "pending" && (
                        <button
                          onClick={() => handleComplete(item)}
                          disabled={isCompleting}
                          title="Mark as complete"
                          className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 opacity-0 transition-opacity group-hover:opacity-100 hover:border-green-300 hover:bg-green-50 hover:text-green-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isCompleting ? (
                            <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          ) : (
                            <CheckIcon />
                          )}
                          Complete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function CheckIcon() {
  return (
    <svg
      className="h-3.5 w-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  );
}

function CircleCheckIcon() {
  return (
    <svg
      className="h-6 w-6 text-gray-400"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  );
}
