"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { ActionItem, createActionItemsApi } from "@/lib/api";
import TaskDetailPanel from "./TaskDetailPanel";

type FilterTab = "pending" | "completed" | "all";

interface Props {
  clientId: string;
  /** Passed so the component can show a helpful empty state if no docs exist. */
  documentCount: number;
  /** Called by parent when it wants to force a refresh (e.g. after upload). */
  refreshKey?: number;
}

export default function ActionItemList({
  clientId,
  documentCount,
  refreshKey = 0,
}: Props) {
  const { getToken } = useAuth();

  const [items, setItems] = useState<ActionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<FilterTab>("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Panel state
  const [selectedItem, setSelectedItem] = useState<ActionItem | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  const api = createActionItemsApi(getToken);

  // ── Fetch ─────────────────────────────────────────────────────────────────

  async function fetchItems(tab: FilterTab = filter) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list(clientId, tab === "all" ? undefined : tab);
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load action items");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchItems(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, filter, refreshKey]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  async function handleToggleComplete(item: ActionItem) {
    setUpdatingId(item.id);
    const newStatus = item.status === "completed" ? "pending" : "completed";
    try {
      const updated = await api.update(item.id, { status: newStatus });
      setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
      // If filtering by pending and item just became completed, remove it
      if (filter === "pending" && newStatus === "completed") {
        setItems((prev) => prev.filter((i) => i.id !== item.id));
        setTotal((t) => t - 1);
      }
      if (filter === "completed" && newStatus === "pending") {
        setItems((prev) => prev.filter((i) => i.id !== item.id));
        setTotal((t) => t - 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update item");
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleDelete(item: ActionItem) {
    setDeletingId(item.id);
    try {
      await api.delete(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      setTotal((t) => t - 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete item");
    } finally {
      setDeletingId(null);
    }
  }

  function handleTabChange(tab: FilterTab) {
    setFilter(tab);
  }

  function openPanel(item: ActionItem | null) {
    setSelectedItem(item);
    setPanelOpen(true);
  }

  function closePanel() {
    setPanelOpen(false);
    setSelectedItem(null);
  }

  function handleSaved(saved: ActionItem) {
    if (selectedItem) {
      // Editing existing
      setItems((prev) => prev.map((i) => (i.id === saved.id ? saved : i)));
    } else {
      // Created new — refresh list
      fetchItems(filter);
    }
  }

  function handleDeleted(id: string) {
    setItems((prev) => prev.filter((i) => i.id !== id));
    setTotal((t) => t - 1);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-gray-900">Action Items</h2>
          {filter === "pending" && total > 0 && (
            <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
              {total}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => openPanel(null)}
            title="Add task"
            className="rounded-lg px-2 py-1 text-xs font-medium text-blue-600 transition-colors hover:bg-blue-50"
          >
            + Add task
          </button>
          <button
            onClick={() => fetchItems(filter)}
            disabled={loading}
            title="Refresh"
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:opacity-40"
          >
            <RefreshIcon spinning={loading} />
          </button>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="mb-3 flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 text-sm">
        {(["pending", "completed", "all"] as FilterTab[]).map((tab) => (
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
        <div className="mb-3 flex items-center justify-between px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
          <span>{error}</span>
          <button onClick={() => fetchItems(filter)} className="text-red-500 underline text-xs">Retry</button>
        </div>
      )}

      {/* Content */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Loading...
          </div>
        ) : items.length === 0 ? (
          <EmptyState filter={filter} documentCount={documentCount} />
        ) : (
          <ul className="divide-y divide-gray-100">
            {items.map((item) => (
              <ActionItemRow
                key={item.id}
                item={item}
                isUpdating={updatingId === item.id}
                isDeleting={deletingId === item.id}
                onToggleComplete={() => handleToggleComplete(item)}
                onDelete={() => handleDelete(item)}
                onClick={() => openPanel(item)}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Detail panel */}
      <TaskDetailPanel
        item={selectedItem}
        isOpen={panelOpen}
        clientId={clientId}
        onClose={closePanel}
        onSaved={handleSaved}
        onDeleted={handleDeleted}
      />
    </div>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function ActionItemRow({
  item,
  isUpdating,
  isDeleting,
  onToggleComplete,
  onDelete,
  onClick,
}: {
  item: ActionItem;
  isUpdating: boolean;
  isDeleting: boolean;
  onToggleComplete: () => void;
  onDelete: () => void;
  onClick: () => void;
}) {
  const busy = isUpdating || isDeleting;
  const done = item.status === "completed";

  return (
    <li className={`flex items-start gap-3 px-4 py-3 ${isDeleting ? "opacity-50" : ""}`}>
      {/* Checkbox */}
      <button
        onClick={(e) => { e.stopPropagation(); onToggleComplete(); }}
        disabled={busy}
        title={done ? "Mark pending" : "Mark complete"}
        className="mt-0.5 shrink-0 rounded text-gray-400 transition-colors hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isUpdating ? (
          <span className="block h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
        ) : done ? (
          <CheckCircleIcon className="h-5 w-5 text-green-500" />
        ) : (
          <CircleIcon className="h-5 w-5" />
        )}
      </button>

      {/* Content — clickable to open panel */}
      <div className="min-w-0 flex-1 cursor-pointer" onClick={onClick}>
        <p
          className={`text-sm leading-snug transition-all duration-200 ${
            done ? "text-gray-400 line-through opacity-60" : "text-gray-800"
          }`}
        >
          {item.text}
        </p>

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          {/* Source document */}
          {item.document_filename && (
            <span className="text-xs text-gray-400 truncate max-w-[180px]">
              {item.document_filename}
            </span>
          )}

          {/* Due date */}
          {item.due_date && (
            <span
              className={`text-xs ${
                isOverdue(item.due_date) && !done
                  ? "font-medium text-red-600"
                  : "text-gray-400"
              }`}
            >
              Due {formatDate(item.due_date)}
            </span>
          )}

          {/* Priority badge */}
          {item.priority && <PriorityBadge priority={item.priority} />}

          {/* Assigned to */}
          {item.assigned_to_name && (
            <span className="text-xs text-gray-400">
              {item.assigned_to_name}
            </span>
          )}
        </div>
      </div>

      {/* Delete */}
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        disabled={busy}
        title="Delete"
        className="shrink-0 rounded-lg p-1 text-gray-300 transition-colors hover:bg-red-50 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isDeleting ? (
          <span className="block h-3.5 w-3.5 rounded-full border-2 border-red-400 border-t-transparent animate-spin" />
        ) : (
          <TrashIcon />
        )}
      </button>
    </li>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({
  filter,
  documentCount,
}: {
  filter: FilterTab;
  documentCount: number;
}) {
  const message =
    documentCount === 0
      ? "Upload documents to automatically extract action items."
      : filter === "completed"
      ? "No completed action items yet."
      : filter === "pending"
      ? "No pending action items — you're all caught up!"
      : "No action items found.";

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
        <ClipboardIcon />
      </div>
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

function ClipboardIcon() {
  return (
    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

// ─── Priority badge ───────────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: "low" | "medium" | "high" }) {
  const styles = {
    high: "bg-red-50 text-red-700",
    medium: "bg-yellow-50 text-yellow-700",
    low: "bg-gray-100 text-gray-500",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-medium capitalize ${styles[priority]}`}
    >
      {priority}
    </span>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function isOverdue(iso: string): boolean {
  return new Date(iso) < new Date(new Date().toDateString());
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function CircleIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}

function CheckCircleIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      className={`h-4 w-4 ${spinning ? "animate-spin" : ""}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
    </svg>
  );
}
