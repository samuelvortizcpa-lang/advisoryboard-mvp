"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ActionItem, createActionItemsApi, OrgMember, createOrganizationsApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import TaskDetailPanel from "@/components/action-items/TaskDetailPanel";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const PRIORITY_BADGE: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-gray-100 text-gray-600",
};

function isOverdue(item: ActionItem): boolean {
  if (!item.due_date || item.status !== "pending") return false;
  return new Date(item.due_date) < new Date(new Date().toDateString());
}

function formatDueDate(iso: string | null): { label: string; className: string } {
  if (!iso) return { label: "—", className: "text-gray-400" };
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
function sortItems(items: ActionItem[]): ActionItem[] {
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
  const { activeOrg } = useOrg();

  const [items, setItems] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<"pending" | "completed" | "all">(
    "pending"
  );
  const [priorityFilter, setPriorityFilter] = useState<"all" | "high" | "medium" | "low">(
    "all"
  );
  const [assignedFilter, setAssignedFilter] = useState<string>("all");

  // Team members for assigned filter
  const [members, setMembers] = useState<OrgMember[]>([]);

  // Quick-complete state
  const [completing, setCompleting] = useState<Set<string>>(new Set());

  // Panel state
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelItem, setPanelItem] = useState<ActionItem | null>(null);

  // Fetch org members
  useEffect(() => {
    if (!activeOrg?.id) return;
    createOrganizationsApi(getToken)
      .listMembers(activeOrg.id)
      .then(setMembers)
      .catch(() => {});
  }, [activeOrg?.id, getToken]);

  // Fetch action items via org-wide endpoint
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const api = createActionItemsApi(getToken, activeOrg?.id);
    const params: Record<string, string> = { limit: "200" };
    if (statusFilter !== "all") params.status = statusFilter;
    if (priorityFilter !== "all") params.priority = priorityFilter;
    if (assignedFilter !== "all") params.assigned_to = assignedFilter;

    api
      .listOrg(params)
      .then((res) => {
        if (!cancelled) setItems(sortItems(res.items));
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
  }, [getToken, activeOrg?.id, statusFilter, priorityFilter, assignedFilter]);

  async function handleToggleComplete(item: ActionItem) {
    const newStatus = item.status === "completed" ? "pending" : "completed";
    setCompleting((prev) => new Set(prev).add(item.id));
    try {
      const updated = await createActionItemsApi(getToken, activeOrg?.id).update(item.id, { status: newStatus });
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, ...updated } : i))
      );
    } catch {
      // Leave item as-is
    } finally {
      setCompleting((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  }

  function openPanel(item: ActionItem | null) {
    setPanelItem(item);
    setPanelOpen(true);
  }

  function closePanel() {
    setPanelOpen(false);
    setPanelItem(null);
  }

  function handlePanelSaved(saved: ActionItem) {
    if (panelItem) {
      setItems((prev) => prev.map((i) => (i.id === saved.id ? saved : i)));
    } else {
      // Created new — re-fetch
      const api = createActionItemsApi(getToken, activeOrg?.id);
      const params: Record<string, string> = { limit: "200" };
      if (statusFilter !== "all") params.status = statusFilter;
      if (priorityFilter !== "all") params.priority = priorityFilter;
      if (assignedFilter !== "all") params.assigned_to = assignedFilter;
      api.listOrg(params).then((res) => setItems(sortItems(res.items))).catch(() => {});
    }
  }

  function handlePanelDeleted(id: string) {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

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
        <button
          onClick={() => openPanel(null)}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600"
        >
          + New action item
        </button>
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

        {/* Assigned to filter */}
        {members.length > 0 && (
          <div className="flex overflow-hidden rounded-md border border-gray-200 bg-white">
            <button
              onClick={() => setAssignedFilter("all")}
              className={[
                "px-3 py-1.5 text-xs font-medium transition-colors",
                assignedFilter === "all"
                  ? "bg-blue-600 text-white"
                  : "text-gray-500 hover:bg-gray-50",
              ].join(" ")}
            >
              All Members
            </button>
            {members.map((m) => (
              <button
                key={m.user_id}
                onClick={() => setAssignedFilter(m.user_id)}
                className={[
                  "px-3 py-1.5 text-xs font-medium transition-colors",
                  assignedFilter === m.user_id
                    ? "bg-blue-600 text-white"
                    : "text-gray-500 hover:bg-gray-50",
                ].join(" ")}
              >
                {m.user_name || m.user_email || "Member"}
              </button>
            ))}
          </div>
        )}
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
      {!loading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white py-20 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
            <CircleCheckIcon />
          </div>
          <p className="text-sm font-medium text-gray-900">
            No items match your filters
          </p>
          <p className="mt-1 text-xs text-gray-400">
            Try adjusting your filters or create a new action item
          </p>
        </div>
      )}

      {/* ── Table ────────────────────────────────────────────────────────── */}
      {!loading && !error && items.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60">
                {["", "Task", "Client", "Priority", "Due Date", "Assigned", "Status", ""].map((h, i) => (
                  <th
                    key={`${h}-${i}`}
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-400"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {items.map((item) => {
                const overdue = isOverdue(item);
                const dueInfo = formatDueDate(item.due_date);
                const isCompleting = completing.has(item.id);

                return (
                  <tr
                    key={item.id}
                    onClick={() => openPanel(item)}
                    className="group cursor-pointer transition-colors hover:bg-gray-50"
                  >
                    {/* Quick-complete circle */}
                    <td className="w-10 px-4 py-3.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleToggleComplete(item); }}
                        disabled={isCompleting}
                        title={item.status === "completed" ? "Mark pending" : "Mark complete"}
                        className="rounded text-gray-400 transition-colors hover:text-blue-600 disabled:opacity-50"
                      >
                        {isCompleting ? (
                          <span className="block h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                        ) : item.status === "completed" ? (
                          <CheckCircleIcon />
                        ) : (
                          <CircleIcon />
                        )}
                      </button>
                    </td>

                    {/* Task — left-border accent when overdue */}
                    <td
                      className={[
                        "max-w-xs px-4 py-3.5",
                        overdue ? "border-l-2 border-l-red-400" : "",
                      ].join(" ")}
                    >
                      <p
                        className={[
                          "text-sm transition-all duration-200",
                          item.status === "completed"
                            ? "text-gray-400 line-through opacity-60"
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
                        onClick={(e) => e.stopPropagation()}
                        className="text-sm text-blue-600 hover:underline"
                      >
                        {item.client_name ?? "—"}
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
                        <span className="text-xs text-gray-400">—</span>
                      )}
                    </td>

                    {/* Due Date */}
                    <td className={["px-4 py-3.5 text-sm", dueInfo.className].join(" ")}>
                      {dueInfo.label}
                    </td>

                    {/* Assigned */}
                    <td className="px-4 py-3.5 text-sm text-gray-600">
                      {item.assigned_to_name || <span className="text-gray-400">—</span>}
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
                          onClick={(e) => { e.stopPropagation(); handleToggleComplete(item); }}
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

      {/* Detail panel */}
      <TaskDetailPanel
        item={panelItem}
        isOpen={panelOpen}
        onClose={closePanel}
        onSaved={handlePanelSaved}
        onDeleted={handlePanelDeleted}
      />
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

function CircleIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg className="h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
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
