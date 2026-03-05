"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ActionItem,
  Document,
  createActionItemsApi,
  createDocumentsApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CalendarDayData {
  actionItems: ActionItem[];
  documents: Document[];
}

/** "YYYY-MM-DD" → CalendarDayData */
type DayMap = Record<string, CalendarDayData>;

interface Props {
  clientId: string;
  /** Increment to trigger a re-fetch (e.g. after an upload) */
  refreshKey?: number;
}

// ─── Static data ──────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_ABBRS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ─── Date helpers ─────────────────────────────────────────────────────────────

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── Dot-color logic ──────────────────────────────────────────────────────────

function actionDotClass(item: ActionItem): string {
  if (item.status === "completed") return "bg-green-500";
  if (item.priority === "high")    return "bg-red-500";
  if (item.priority === "medium")  return "bg-yellow-400";
  return "bg-gray-400"; // low or no priority
}

function actionPriorityTextClass(item: ActionItem): string {
  if (item.status === "completed") return "text-green-600";
  if (item.priority === "high")    return "text-red-600";
  if (item.priority === "medium")  return "text-yellow-600";
  return "text-gray-500";
}

// ─── Calendar grid builder ────────────────────────────────────────────────────

/**
 * Returns an array of 35 or 42 entries (whole weeks) where null = filler cell
 * before/after the month's days.
 */
function buildCalendarCells(year: number, month: number): (Date | null)[] {
  const firstWeekday = new Date(year, month, 1).getDay(); // 0 = Sun
  const daysInMonth  = new Date(year, month + 1, 0).getDate();

  const cells: (Date | null)[] = [];

  // Leading filler cells
  for (let i = 0; i < firstWeekday; i++) cells.push(null);

  // Actual month days
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));

  // Trailing filler to complete the last row
  while (cells.length % 7 !== 0) cells.push(null);

  return cells;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function CalendarView({ clientId, refreshKey = 0 }: Props) {
  const { getToken } = useAuth();

  // Snapshot "today" once; stable for the lifetime of the component.
  const [today] = useState(() => new Date());
  const todayKey = toDateKey(today);

  // ── Viewed month state ────────────────────────────────────────────────────
  const [year,  setYear]  = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-indexed

  // ── Data state ────────────────────────────────────────────────────────────
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [documents,   setDocuments]   = useState<Document[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);
  const [retryCount,  setRetryCount]  = useState(0);

  // ── Popover state ─────────────────────────────────────────────────────────
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // ── Fetch data ───────────────────────────────────────────────────────────

  useEffect(() => {
    setLoading(true);
    setError(null);

    // Fetch all items (limit=500 handles most real-world client datasets)
    Promise.all([
      createActionItemsApi(getToken).list(clientId, undefined, 0, 500),
      createDocumentsApi(getToken).list(clientId, 0, 500),
    ])
      .then(([actRes, docRes]) => {
        setActionItems(actRes.items);
        setDocuments(docRes.items);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [clientId, getToken, refreshKey, retryCount]);

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
    document.addEventListener("keydown",   onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown",   onKeyDown);
    };
  }, [selectedKey]);

  // ── Build day map ─────────────────────────────────────────────────────────

  const dayMap = useMemo<DayMap>(() => {
    const map: DayMap = {};

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

    return map;
  }, [actionItems, documents]);

  // ── Calendar grid ─────────────────────────────────────────────────────────

  const cells = useMemo(() => buildCalendarCells(year, month), [year, month]);

  const hasEventsThisMonth = useMemo(
    () => cells.some((cell) => cell !== null && !!dayMap[toDateKey(cell)]),
    [cells, dayMap]
  );

  // ── Month navigation ──────────────────────────────────────────────────────

  function goToPrev() {
    setSelectedKey(null);
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  }

  function goToNext() {
    setSelectedKey(null);
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  }

  function goToToday() {
    setSelectedKey(null);
    setYear(today.getFullYear());
    setMonth(today.getMonth());
  }

  // ── Selected day data for popover ─────────────────────────────────────────

  const selectedDayData = selectedKey ? (dayMap[selectedKey] ?? null) : null;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">

      {/* ── Calendar header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-gray-900">
            {MONTH_NAMES[month]} {year}
          </h2>
          <button
            onClick={goToToday}
            className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Today
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={goToPrev}
            aria-label="Previous month"
            className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
          >
            <ChevronLeftIcon />
          </button>
          <button
            onClick={goToNext}
            aria-label="Next month"
            className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
          >
            <ChevronRightIcon />
          </button>
        </div>
      </div>

      {/* ── Loading spinner ──────────────────────────────────────────────── */}
      {loading && (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          Loading...
        </div>
      )}

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {!loading && error && (
        <div className="mx-4 mb-4 flex items-center justify-between px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
          <span>{error}</span>
          <button onClick={() => setRetryCount(c => c + 1)} className="text-red-500 underline text-xs">Retry</button>
        </div>
      )}

      {/* ── Calendar grid ────────────────────────────────────────────────── */}
      {!loading && !error && (
        <div className="px-3 pb-3 pt-2">

          {/* Day-of-week header row */}
          <div className="grid grid-cols-7">
            {DAY_ABBRS.map((d) => (
              <div
                key={d}
                className="py-1.5 text-center text-[11px] font-semibold uppercase tracking-wide text-gray-400"
              >
                {d}
              </div>
            ))}
          </div>

          {/*
            1-px gaps between cells create the grid lines.
            bg-gray-100 on the container shows through the gaps.
          */}
          {!hasEventsThisMonth && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
                <CalendarEmptyIcon />
              </div>
              <p className="text-sm text-gray-400">No events this month</p>
            </div>
          )}

          <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-gray-100 bg-gray-100">
            {cells.map((cellDate, idx) => {
              // ── Filler cell ──────────────────────────────────────────
              if (!cellDate) {
                return (
                  <div
                    key={`filler-${idx}`}
                    className="min-h-[76px] bg-gray-50"
                  />
                );
              }

              const key       = toDateKey(cellDate);
              const data      = dayMap[key];
              const isToday   = key === todayKey;
              const isSelected = key === selectedKey;
              const dayNum    = cellDate.getDate();

              // Dots: up to MAX_DOTS action dots then document dots, with "+N" overflow
              const MAX_DOTS = 4;
              const aDots = data?.actionItems ?? [];
              const dDots = data?.documents   ?? [];
              const total = aDots.length + dDots.length;

              const shownA  = aDots.slice(0, Math.min(MAX_DOTS, aDots.length));
              const slots   = MAX_DOTS - shownA.length;
              const shownD  = dDots.slice(0, Math.max(0, slots));
              const overflow = total - shownA.length - shownD.length;

              return (
                <button
                  key={key}
                  onClick={() => setSelectedKey(isSelected ? null : key)}
                  className={[
                    "flex min-h-[76px] flex-col bg-white p-1.5 text-left transition-colors hover:bg-indigo-50/50",
                    isSelected
                      ? "ring-2 ring-inset ring-indigo-400 bg-indigo-50/50"
                      : "",
                  ].join(" ")}
                >
                  {/* Day number */}
                  <span
                    className={[
                      "mb-1 inline-flex h-6 w-6 items-center justify-center rounded-full text-[13px] font-medium leading-none",
                      isToday
                        ? "bg-indigo-600 text-white"
                        : "text-gray-700",
                    ].join(" ")}
                  >
                    {dayNum}
                  </span>

                  {/* Dot row */}
                  {total > 0 && (
                    <div className="flex flex-wrap items-center gap-[3px] px-0.5">
                      {shownA.map((item) => (
                        <span
                          key={item.id}
                          title={item.text}
                          className={`block h-[6px] w-[6px] rounded-full ${actionDotClass(item)}`}
                        />
                      ))}
                      {shownD.map((doc) => (
                        <span
                          key={doc.id}
                          title={doc.filename}
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
      )}

      {/* ── Legend ───────────────────────────────────────────────────────── */}
      {!loading && !error && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-gray-100 px-5 py-3">
          <LegendItem dotClass="bg-red-500"    label="High priority" />
          <LegendItem dotClass="bg-yellow-400" label="Medium priority" />
          <LegendItem dotClass="bg-gray-400"   label="Low priority" />
          <LegendItem dotClass="bg-green-500"  label="Completed" />
          <LegendItem dotClass="bg-blue-500"   label="Document" />
        </div>
      )}

      {/* ── Day-detail popover ────────────────────────────────────────────
          Fixed overlay: clicking the scrim or pressing Escape closes it.
      ─────────────────────────────────────────────────────────────────── */}
      {selectedKey && (
        <div
          className="fixed inset-0 z-40 flex items-start justify-center px-4 pt-24 bg-black/20"
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
            <div className="max-h-72 overflow-y-auto divide-y divide-gray-50">

              {/* ── Action items ───────────────────────────────────────── */}
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
                            className={`text-sm leading-snug ${
                              item.status === "completed"
                                ? "text-gray-400 line-through"
                                : "text-gray-800"
                            }`}
                          >
                            {item.text}
                          </p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
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
                            {item.document_filename && (
                              <span className="max-w-[160px] truncate text-xs text-gray-400">
                                {item.document_filename}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* ── Documents ──────────────────────────────────────────── */}
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
                          <p className="mt-0.5 text-xs text-gray-400">
                            <span className="font-medium uppercase">{doc.file_type}</span>
                            {" · "}
                            {formatBytes(doc.file_size)}
                            {!doc.processed && (
                              <span className="ml-1.5 text-amber-500">· Processing…</span>
                            )}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* ── Empty state ────────────────────────────────────────── */}
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

function CalendarEmptyIcon() {
  return (
    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  );
}

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
