"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ActionItem,
  Document,
  createActionItemsApi,
  createClientsApi,
  createDocumentsApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type EnrichedActionItem = ActionItem & { clientName: string };
type EnrichedDocument = Document & { clientName: string };

interface EnrichedDayEntry {
  actionItems: EnrichedActionItem[];
  documents: EnrichedDocument[];
}

type DayMap = Record<string, EnrichedDayEntry>;

// ─── Static data ──────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_ABBRS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ─── Date helpers (copied from CalendarView.tsx) ──────────────────────────────

/**
 * Parse an ISO date/datetime string into a local-timezone Date, avoiding the
 * UTC midnight → previous day shift that `new Date("YYYY-MM-DD")` causes.
 */
function parseLocalDate(iso: string): Date {
  const datePart = iso.split("T")[0]; // "YYYY-MM-DD"
  const [y, m, d] = datePart.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Canonical "YYYY-MM-DD" key for a local Date. */
function toDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Human-readable date for the popover header. */
function formatDateDisplay(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Returns an array of 35 or 42 entries (whole weeks) where null = filler cell
 * before/after the month's days.
 */
function buildCalendarCells(year: number, month: number): (Date | null)[] {
  const firstWeekday = new Date(year, month, 1).getDay(); // 0 = Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (Date | null)[] = [];

  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);

  return cells;
}

// ─── Dot-color logic (same as CalendarView.tsx) ───────────────────────────────

function actionDotClass(item: ActionItem): string {
  if (item.status === "completed") return "bg-green-500";
  if (item.priority === "high") return "bg-red-500";
  if (item.priority === "medium") return "bg-yellow-400";
  return "bg-gray-400"; // low or no priority
}

function actionPriorityTextClass(item: ActionItem): string {
  if (item.status === "completed") return "text-green-600";
  if (item.priority === "high") return "text-red-600";
  if (item.priority === "medium") return "text-yellow-600";
  return "text-gray-500";
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CalendarPage() {
  const { getToken } = useAuth();

  // Snapshot "today" once; stable for the lifetime of the component.
  const [today] = useState(() => new Date());
  const todayKey = toDateKey(today);

  // ── Month navigation state ────────────────────────────────────────────────
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-indexed

  // ── Data state ────────────────────────────────────────────────────────────
  const [dayMap, setDayMap] = useState<DayMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Popover state ─────────────────────────────────────────────────────────
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // ── Fetch all clients then their action items + documents in parallel ─────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const clientsApi = createClientsApi(getToken);
    const actionItemsApi = createActionItemsApi(getToken);
    const documentsApi = createDocumentsApi(getToken);

    clientsApi
      .list(0, 200)
      .then(async (clientsResp) => {
        const clients = clientsResp.items;

        // Fetch action items + documents per client; tolerate individual failures
        const results = await Promise.allSettled(
          clients.map(async (client) => {
            const [actResp, docResp] = await Promise.all([
              actionItemsApi.list(client.id, undefined, 0, 500),
              documentsApi.list(client.id, 0, 500),
            ]);
            return {
              actionItems: actResp.items.map(
                (item): EnrichedActionItem => ({ ...item, clientName: client.name })
              ),
              documents: docResp.items.map(
                (doc): EnrichedDocument => ({ ...doc, clientName: client.name })
              ),
            };
          })
        );

        if (cancelled) return;

        // Build the day map from all successful fetches
        const map: DayMap = {};

        for (const result of results) {
          if (result.status !== "fulfilled") continue;
          const { actionItems, documents } = result.value;

          for (const item of actionItems) {
            if (!item.due_date) continue;
            const key = toDateKey(parseLocalDate(item.due_date));
            if (!map[key]) map[key] = { actionItems: [], documents: [] };
            map[key].actionItems.push(item);
          }

          for (const doc of documents) {
            const key = toDateKey(parseLocalDate(doc.upload_date));
            if (!map[key]) map[key] = { actionItems: [], documents: [] };
            map[key].documents.push(doc);
          }
        }

        setDayMap(map);
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

  // ── Close popover on outside click / Escape ───────────────────────────────
  useEffect(() => {
    if (!selectedKey) return;

    function onMouseDown(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setSelectedKey(null);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setSelectedKey(null);
    }

    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [selectedKey]);

  // ── Month navigation ──────────────────────────────────────────────────────
  function goToPrev() {
    setSelectedKey(null);
    if (month === 0) { setYear((y) => y - 1); setMonth(11); }
    else setMonth((m) => m - 1);
  }
  function goToNext() {
    setSelectedKey(null);
    if (month === 11) { setYear((y) => y + 1); setMonth(0); }
    else setMonth((m) => m + 1);
  }
  function goToToday() {
    setSelectedKey(null);
    setYear(today.getFullYear());
    setMonth(today.getMonth());
  }

  // ── This Week: Sun–Sat of the current week ────────────────────────────────
  const weekDays = useMemo(() => {
    const startOfWeek = new Date(today);
    startOfWeek.setDate(today.getDate() - today.getDay()); // back to Sunday
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(startOfWeek);
      d.setDate(startOfWeek.getDate() + i);
      return d;
    });
  }, [today]);

  // ── Calendar grid cells ───────────────────────────────────────────────────
  const cells = useMemo(() => buildCalendarCells(year, month), [year, month]);

  const selectedDayData = selectedKey ? (dayMap[selectedKey] ?? null) : null;

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="px-8 py-8">

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Calendar</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            All clients · {MONTH_NAMES[month]} {year}
          </p>
        </div>

        {/* Month navigation */}
        <div className="flex items-center gap-2">
          <button
            onClick={goToToday}
            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Today
          </button>
          <div className="flex items-center">
            <button
              onClick={goToPrev}
              aria-label="Previous month"
              className="rounded-l-md border border-gray-200 bg-white p-1.5 text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700"
            >
              <ChevronLeftIcon />
            </button>
            <button
              onClick={goToNext}
              aria-label="Next month"
              className="rounded-r-md border-y border-r border-gray-200 bg-white p-1.5 text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700"
            >
              <ChevronRightIcon />
            </button>
          </div>
        </div>
      </div>

      {/* ── Loading ────────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      )}

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {/* ── This Week strip ──────────────────────────────────────────────── */}
          <div className="mb-5 overflow-hidden rounded-xl border border-gray-200 bg-white">
            <div className="border-b border-gray-100 px-5 py-2.5">
              <h2 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                This Week
              </h2>
            </div>

            <div className="grid grid-cols-7">
              {weekDays.map((day) => {
                const key = toDateKey(day);
                const data = dayMap[key];
                const isToday = key === todayKey;

                const aDots = (data?.actionItems ?? []).slice(0, 4);
                const dDots = (data?.documents ?? []).slice(0, Math.max(0, 4 - aDots.length));
                const totalCount = (data?.actionItems?.length ?? 0) + (data?.documents?.length ?? 0);
                const overflow = totalCount - aDots.length - dDots.length;
                const hasItems = totalCount > 0;

                return (
                  <button
                    key={key}
                    onClick={() => {
                      if (hasItems) {
                        // Navigate month to the week-day's month if needed
                        setYear(day.getFullYear());
                        setMonth(day.getMonth());
                        setSelectedKey(key);
                      }
                    }}
                    disabled={!hasItems}
                    className={[
                      "flex flex-col items-center gap-1.5 border-r border-gray-100 px-2 py-3 last:border-r-0 transition-colors",
                      hasItems ? "hover:bg-gray-50" : "cursor-default",
                      isToday ? "bg-blue-50/40" : "",
                    ].join(" ")}
                  >
                    {/* Day abbr */}
                    <span
                      className={[
                        "text-[11px] font-semibold uppercase tracking-wide",
                        isToday ? "text-blue-600" : "text-gray-400",
                      ].join(" ")}
                    >
                      {DAY_ABBRS[day.getDay()]}
                    </span>

                    {/* Date circle */}
                    <span
                      className={[
                        "flex h-6 w-6 items-center justify-center rounded-full text-sm font-medium",
                        isToday ? "bg-blue-600 text-white" : "text-gray-700",
                      ].join(" ")}
                    >
                      {day.getDate()}
                    </span>

                    {/* Dot cluster */}
                    {hasItems ? (
                      <div className="flex flex-wrap justify-center gap-[3px]">
                        {aDots.map((item) => (
                          <span
                            key={item.id}
                            className={`h-[5px] w-[5px] rounded-full ${actionDotClass(item)}`}
                          />
                        ))}
                        {dDots.map((doc) => (
                          <span
                            key={doc.id}
                            className="h-[5px] w-[5px] rounded-full bg-blue-500"
                          />
                        ))}
                        {overflow > 0 && (
                          <span className="text-[9px] font-medium leading-none text-gray-400">
                            +{overflow}
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="h-[10px]" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* ── Legend ───────────────────────────────────────────────────────── */}
          <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <LegendItem dotClass="bg-red-500"    label="High priority" />
            <LegendItem dotClass="bg-yellow-400" label="Medium priority" />
            <LegendItem dotClass="bg-gray-400"   label="Low priority" />
            <LegendItem dotClass="bg-green-500"  label="Completed" />
            <LegendItem dotClass="bg-blue-500"   label="Document" />
          </div>

          {/* ── Monthly calendar grid ─────────────────────────────────────────── */}
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
            {/* Day-of-week header */}
            <div className="grid grid-cols-7 border-b border-gray-100 bg-gray-50/60">
              {DAY_ABBRS.map((d) => (
                <div
                  key={d}
                  className="py-2 text-center text-[11px] font-semibold uppercase tracking-wide text-gray-400"
                >
                  {d}
                </div>
              ))}
            </div>

            {/* Cell grid — 1 px gaps via bg-gray-100 on container */}
            <div className="grid grid-cols-7 gap-px bg-gray-100">
              {cells.map((cellDate, idx) => {
                // Filler cell
                if (!cellDate) {
                  return <div key={`filler-${idx}`} className="min-h-[80px] bg-gray-50" />;
                }

                const key = toDateKey(cellDate);
                const data = dayMap[key];
                const isToday = key === todayKey;
                const isSelected = key === selectedKey;

                const MAX_DOTS = 4;
                const aDots = data?.actionItems ?? [];
                const dDots = data?.documents ?? [];
                const total = aDots.length + dDots.length;

                const shownA = aDots.slice(0, Math.min(MAX_DOTS, aDots.length));
                const slots = MAX_DOTS - shownA.length;
                const shownD = dDots.slice(0, Math.max(0, slots));
                const overflow = total - shownA.length - shownD.length;

                return (
                  <button
                    key={key}
                    onClick={() => setSelectedKey(isSelected ? null : key)}
                    className={[
                      "flex min-h-[80px] flex-col bg-white p-1.5 text-left transition-colors hover:bg-indigo-50/50",
                      isSelected ? "ring-2 ring-inset ring-indigo-400 bg-indigo-50/50" : "",
                    ].join(" ")}
                  >
                    {/* Day number */}
                    <span
                      className={[
                        "mb-1 inline-flex h-6 w-6 items-center justify-center rounded-full text-[13px] font-medium leading-none",
                        isToday ? "bg-indigo-600 text-white" : "text-gray-700",
                      ].join(" ")}
                    >
                      {cellDate.getDate()}
                    </span>

                    {/* Dot row */}
                    {total > 0 && (
                      <div className="flex flex-wrap items-center gap-[3px] px-0.5">
                        {shownA.map((item) => (
                          <span
                            key={item.id}
                            title={`${item.clientName}: ${item.text}`}
                            className={`block h-[6px] w-[6px] rounded-full ${actionDotClass(item)}`}
                          />
                        ))}
                        {shownD.map((doc) => (
                          <span
                            key={doc.id}
                            title={`${doc.clientName}: ${doc.filename}`}
                            className="block h-[6px] w-[6px] rounded-full bg-blue-500"
                          />
                        ))}
                        {overflow > 0 && (
                          <span className="text-[10px] leading-none font-medium text-gray-400">
                            +{overflow}
                          </span>
                        )}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* ── Day-detail popover ─────────────────────────────────────────────────
          Fixed overlay; clicking the scrim or pressing Escape closes it.
      ────────────────────────────────────────────────────────────────────── */}
      {selectedKey && (
        <div
          className="fixed inset-0 z-40 flex items-start justify-center bg-black/20 px-4 pt-24"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedKey(null);
          }}
        >
          <div
            ref={popoverRef}
            role="dialog"
            aria-modal="true"
            aria-label={selectedKey ? formatDateDisplay(selectedKey) : undefined}
            className="w-full max-w-sm overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl"
          >
            {/* Popover header */}
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <p className="text-sm font-semibold text-gray-900">
                {formatDateDisplay(selectedKey)}
              </p>
              <button
                onClick={() => setSelectedKey(null)}
                aria-label="Close"
                className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
              >
                <CloseIcon />
              </button>
            </div>

            {/* Popover body */}
            <div className="max-h-80 divide-y divide-gray-50 overflow-y-auto">

              {/* Action items */}
              {selectedDayData && selectedDayData.actionItems.length > 0 && (
                <div className="px-4 py-3">
                  <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                    Action Items
                  </p>
                  <ul className="space-y-2.5">
                    {selectedDayData.actionItems.map((item) => (
                      <li key={item.id} className="flex items-start gap-2.5">
                        <span
                          className={`mt-[5px] h-2 w-2 shrink-0 rounded-full ${actionDotClass(item)}`}
                        />
                        <div className="min-w-0 flex-1">
                          <p
                            className={[
                              "text-sm leading-snug",
                              item.status === "completed"
                                ? "text-gray-400 line-through"
                                : "text-gray-800",
                            ].join(" ")}
                          >
                            {item.text}
                          </p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
                            {/* Client name → client actions tab */}
                            <Link
                              href={`/dashboard/clients/${item.client_id}?tab=actions`}
                              className="text-xs font-medium text-blue-600 hover:underline"
                            >
                              {item.clientName}
                            </Link>
                            {item.priority && (
                              <span
                                className={`text-xs capitalize font-medium ${actionPriorityTextClass(item)}`}
                              >
                                {item.status === "completed" ? "completed" : item.priority}
                              </span>
                            )}
                            {!item.priority && (
                              <span className="text-xs capitalize text-gray-400">
                                {item.status}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Documents */}
              {selectedDayData && selectedDayData.documents.length > 0 && (
                <div className="px-4 py-3">
                  <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                    Documents Uploaded
                  </p>
                  <ul className="space-y-2.5">
                    {selectedDayData.documents.map((doc) => (
                      <li key={doc.id} className="flex items-start gap-2.5">
                        <span className="mt-[5px] h-2 w-2 shrink-0 rounded-full bg-blue-500" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-gray-800">{doc.filename}</p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
                            {/* Client name → client documents tab */}
                            <Link
                              href={`/dashboard/clients/${doc.client_id}?tab=documents`}
                              className="text-xs font-medium text-blue-600 hover:underline"
                            >
                              {doc.clientName}
                            </Link>
                            <span className="text-xs text-gray-400">
                              <span className="font-medium uppercase">{doc.file_type}</span>
                            </span>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Empty state */}
              {(!selectedDayData ||
                (selectedDayData.actionItems.length === 0 &&
                  selectedDayData.documents.length === 0)) && (
                <p className="px-4 py-6 text-center text-sm text-gray-400">
                  No items for this day.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function LegendItem({ dotClass, label }: { dotClass: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      <span className="text-xs text-gray-500">{label}</span>
    </div>
  );
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function ChevronLeftIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
