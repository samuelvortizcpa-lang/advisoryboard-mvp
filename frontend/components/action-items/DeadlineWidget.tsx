"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { ActionItem, createActionItemsApi } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  clientId: string;
  refreshKey?: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Returns how many whole calendar days separate `iso` from today.
 * Negative = overdue, 0 = today, positive = future.
 *
 * Uses local-date arithmetic (split on "T", avoid UTC-midnight shift).
 */
function diffCalendarDays(iso: string): number {
  const datePart = iso.split("T")[0];
  const [y, m, d] = datePart.split("-").map(Number);
  const dueStart   = new Date(y, m - 1, d).getTime();
  const todayStart = new Date(
    new Date().getFullYear(),
    new Date().getMonth(),
    new Date().getDate()
  ).getTime();
  return Math.round((dueStart - todayStart) / 86_400_000);
}

interface RelativeLabel {
  text: string;
  overdue: boolean;
  urgent: boolean; // due today or tomorrow
}

function relativeLabel(iso: string): RelativeLabel {
  const diff = diffCalendarDays(iso);
  if (diff < 0) {
    const n = Math.abs(diff);
    return {
      text: `Overdue by ${n} ${n === 1 ? "day" : "days"}`,
      overdue: true,
      urgent: false,
    };
  }
  if (diff === 0) return { text: "Due today",  overdue: false, urgent: true };
  if (diff === 1) return { text: "Tomorrow",   overdue: false, urgent: true };
  if (diff <= 7)  return { text: `In ${diff} days`, overdue: false, urgent: false };
  const [y, m, d] = iso.split("T")[0].split("-").map(Number);
  const label = new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  return { text: label, overdue: false, urgent: false };
}

// ─── Priority badge ───────────────────────────────────────────────────────────

const PRIORITY_STYLES: Record<string, string> = {
  high:   "bg-red-50 text-red-700 ring-1 ring-red-200",
  medium: "bg-yellow-50 text-yellow-700 ring-1 ring-yellow-200",
  low:    "bg-gray-100 text-gray-500",
};

function PriorityBadge({ priority }: { priority: NonNullable<ActionItem["priority"]> }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-1.5 py-0.5 text-[11px] font-medium capitalize ${
        PRIORITY_STYLES[priority] ?? PRIORITY_STYLES.low
      }`}
    >
      {priority}
    </span>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

const MAX_ITEMS = 7;

export default function DeadlineWidget({ clientId, refreshKey = 0 }: Props) {
  const { getToken } = useAuth();

  const [items, setItems] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completingId, setCompletingId] = useState<string | null>(null);

  const api = createActionItemsApi(getToken);

  // ── Fetch ───────────────────────────────────────────────────────────────────

  function fetchData() {
    setLoading(true);
    setError(null);

    api
      .list(clientId, "pending", 0, 100)
      .then((res) => {
        const sorted = res.items
          .filter((i) => i.due_date !== null)
          // Sort ascending: overdue (negative diff) first, then nearest future
          .sort((a, b) => {
            const [ay, am, ad] = a.due_date!.split("T")[0].split("-").map(Number);
            const [by, bm, bd] = b.due_date!.split("T")[0].split("-").map(Number);
            return (
              new Date(ay, am - 1, ad).getTime() -
              new Date(by, bm - 1, bd).getTime()
            );
          })
          .slice(0, MAX_ITEMS);
        setItems(sorted);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, refreshKey]);

  // ── Mark complete ───────────────────────────────────────────────────────────

  async function handleComplete(item: ActionItem) {
    setCompletingId(item.id);
    try {
      await api.update(item.id, { status: "completed" });
      // Optimistically remove from the list
      setItems((prev) => prev.filter((i) => i.id !== item.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update item");
    } finally {
      setCompletingId(null);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">

      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-900">Upcoming Deadlines</h2>
          {!loading && items.length > 0 && (
            <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
              {items.length}
            </span>
          )}
        </div>

        {/* Subtle reload button */}
        <button
          onClick={fetchData}
          disabled={loading}
          aria-label="Refresh deadlines"
          className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-40"
        >
          <RefreshIcon spinning={loading} />
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-1 mt-3 flex items-center justify-between px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
          <span>{error}</span>
          <button onClick={fetchData} className="text-red-500 underline text-xs">Retry</button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          Loading...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
            <CalendarEmptyIcon />
          </div>
          <p className="text-sm text-gray-500">No upcoming deadlines</p>
        </div>
      )}

      {/* Item list */}
      {!loading && items.length > 0 && (
        <ul className="divide-y divide-gray-50">
          {items.map((item) => {
            const label      = relativeLabel(item.due_date!);
            const completing = completingId === item.id;

            return (
              <li
                key={item.id}
                className={[
                  "flex items-center gap-3 px-4 py-3 transition-colors",
                  label.overdue ? "bg-red-50/60" : "",
                ].join(" ")}
              >
                {/* Quick-complete checkbox */}
                <button
                  onClick={() => handleComplete(item)}
                  disabled={completing}
                  aria-label="Mark complete"
                  title="Mark complete"
                  className="shrink-0 text-gray-400 transition-colors hover:text-green-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {completing ? (
                    <span className="block h-[18px] w-[18px] animate-spin rounded-full border-2 border-green-500 border-t-transparent" />
                  ) : (
                    <CircleIcon />
                  )}
                </button>

                {/* Task text */}
                <p
                  className="min-w-0 flex-1 truncate text-sm text-gray-800"
                  title={item.text}
                >
                  {item.text}
                </p>

                {/* Priority badge — only when set */}
                {item.priority && <PriorityBadge priority={item.priority} />}

                {/* Relative due-date label */}
                <span
                  className={[
                    "shrink-0 text-xs font-medium",
                    label.overdue ? "text-red-600" : label.urgent ? "text-amber-600" : "text-gray-400",
                  ].join(" ")}
                >
                  {label.text}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function CalendarEmptyIcon() {
  return (
    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  );
}

function CircleIcon() {
  return (
    <svg
      className="h-[18px] w-[18px]"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <circle cx="12" cy="12" r="9" />
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
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
      />
    </svg>
  );
}
