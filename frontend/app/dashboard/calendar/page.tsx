"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ActionItem,
  Client,
  createActionItemsApi,
  createClientsApi,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import TaskDetailPanel from "@/components/action-items/TaskDetailPanel";

// ─── Types ────────────────────────────────────────────────────────────────────

type EnrichedActionItem = ActionItem & { clientName: string };

interface EnrichedDayEntry {
  actionItems: EnrichedActionItem[];
}

type DayMap = Record<string, EnrichedDayEntry>;

// ─── Static data ──────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_ABBRS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ─── Date helpers ─────────────────────────────────────────────────────────────

function parseLocalDate(iso: string): Date {
  const datePart = iso.split("T")[0];
  const [y, m, d] = datePart.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function toDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatDateDisplay(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function buildCalendarCells(year: number, month: number): (Date | null)[] {
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (Date | null)[] = [];

  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);

  return cells;
}

// ─── Dot-color logic ──────────────────────────────────────────────────────────

function actionDotClass(item: ActionItem): string {
  if (item.status === "completed") return "bg-green-500";
  if (item.priority === "high") return "bg-red-500";
  if (item.priority === "medium") return "bg-yellow-400";
  return "bg-gray-400";
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
  const { activeOrg } = useOrg();

  const [today] = useState(() => new Date());
  const todayKey = toDateKey(today);

  // ── Month navigation state ────────────────────────────────────────────────
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());

  // ── Data state ────────────────────────────────────────────────────────────
  const [dayMap, setDayMap] = useState<DayMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Client filter state ───────────────────────────────────────────────────
  const [clientFilter, setClientFilter] = useState<string>("");
  const [clients, setClients] = useState<Client[]>([]);

  // ── Popover state ─────────────────────────────────────────────────────────
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // ── TaskDetailPanel state ─────────────────────────────────────────────────
  const [panelItem, setPanelItem] = useState<ActionItem | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [createDate, setCreateDate] = useState<string | null>(null);

  // ── Fetch clients once ────────────────────────────────────────────────────
  useEffect(() => {
    createClientsApi(getToken, activeOrg?.id)
      .list(0, 200)
      .then((r) => setClients(r.items))
      .catch(() => {});
  }, [getToken, activeOrg?.id]);

  // ── Fetch action items for the visible month ──────────────────────────────
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const api = createActionItemsApi(getToken, activeOrg?.id);
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const params: Record<string, string> = {
        due_after: `${year}-${String(month + 1).padStart(2, "0")}-01`,
        due_before: `${year}-${String(month + 1).padStart(2, "0")}-${String(daysInMonth).padStart(2, "0")}`,
        limit: "200",
        sort: "due_date",
      };
      if (clientFilter) params.client_id = clientFilter;

      const res = await api.listOrg(params);

      // Build client name lookup from local clients list
      const clientMap = new Map(clients.map((c) => [c.id, c.name]));

      const map: DayMap = {};
      for (const item of res.items) {
        if (!item.due_date) continue;
        const key = toDateKey(parseLocalDate(item.due_date));
        if (!map[key]) map[key] = { actionItems: [] };
        map[key].actionItems.push({
          ...item,
          clientName: item.client_name ?? clientMap.get(item.client_id) ?? "Unknown",
        });
      }
      setDayMap(map);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load calendar data");
    } finally {
      setLoading(false);
    }
  }, [getToken, activeOrg?.id, year, month, clientFilter, clients]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
    startOfWeek.setDate(today.getDate() - today.getDay());
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(startOfWeek);
      d.setDate(startOfWeek.getDate() + i);
      return d;
    });
  }, [today]);

  // ── Calendar grid cells ───────────────────────────────────────────────────
  const cells = useMemo(() => buildCalendarCells(year, month), [year, month]);

  const selectedDayData = selectedKey ? (dayMap[selectedKey] ?? null) : null;

  // ── TaskDetailPanel handlers ──────────────────────────────────────────────
  function openPanelForItem(item: ActionItem) {
    setPanelItem(item);
    setCreateDate(null);
    setPanelOpen(true);
  }

  function openPanelForCreate(dateKey: string) {
    setPanelItem(null);
    setCreateDate(dateKey);
    setPanelOpen(true);
  }

  function handlePanelSaved() {
    setPanelOpen(false);
    fetchData();
  }

  function handlePanelDeleted() {
    setPanelOpen(false);
    fetchData();
  }

  // ── Pill rendering helper ─────────────────────────────────────────────────
  const MAX_PILLS = 3;

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="px-8 py-8">

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Calendar</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              {clientFilter ? clients.find((c) => c.id === clientFilter)?.name : "All clients"} · {MONTH_NAMES[month]} {year}
            </p>
          </div>

          {/* Client filter */}
          <select
            value={clientFilter}
            onChange={(e) => setClientFilter(e.target.value)}
            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            <option value="">All clients</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
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

                const aiCount = data?.actionItems?.length ?? 0;
                const hasOverdue = data?.actionItems?.some(
                  (i) => i.status === "pending" && i.due_date && parseLocalDate(i.due_date) < today
                ) ?? false;

                return (
                  <button
                    key={key}
                    onClick={() => {
                      setYear(day.getFullYear());
                      setMonth(day.getMonth());
                      if (aiCount > 0) {
                        setSelectedKey(key);
                      }
                    }}
                    className={[
                      "flex flex-col items-center gap-1.5 border-r border-gray-100 px-2 py-3 last:border-r-0 transition-colors",
                      "hover:bg-gray-50",
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

                    {/* Count badge */}
                    {aiCount > 0 ? (
                      <span
                        className={[
                          "inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none",
                          hasOverdue
                            ? "bg-red-100 text-red-700"
                            : "bg-amber-100 text-amber-700",
                        ].join(" ")}
                      >
                        {aiCount}
                      </span>
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
            {/* TODO: add org-wide documents endpoint to populate document events */}
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

            {/* Cell grid */}
            <div className="grid grid-cols-7 gap-px bg-gray-100">
              {cells.map((cellDate, idx) => {
                if (!cellDate) {
                  return <div key={`filler-${idx}`} className="min-h-[100px] bg-gray-50" />;
                }

                const key = toDateKey(cellDate);
                const data = dayMap[key];
                const isToday = key === todayKey;
                const isSelected = key === selectedKey;

                const items = data?.actionItems ?? [];
                const shownItems = items.slice(0, MAX_PILLS);
                const overflow = items.length - MAX_PILLS;

                return (
                  <div
                    key={key}
                    onClick={() => openPanelForCreate(key)}
                    className={[
                      "flex min-h-[100px] flex-col bg-white p-1.5 text-left transition-colors hover:bg-indigo-50/50 cursor-pointer",
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

                    {/* Action item pills */}
                    <div className="flex flex-col gap-0.5">
                      {shownItems.map((item) => (
                        <button
                          key={item.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            openPanelForItem(item);
                          }}
                          className="flex items-center gap-1 px-1 py-0.5 rounded text-[11px] cursor-pointer hover:bg-gray-100 truncate text-left"
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full shrink-0 ${actionDotClass(item)}`}
                          />
                          <span
                            className={[
                              "truncate",
                              item.status === "completed"
                                ? "text-gray-400 line-through opacity-60"
                                : "text-gray-700",
                            ].join(" ")}
                          >
                            {item.text.length > 25 ? item.text.slice(0, 25) + "…" : item.text}
                          </span>
                        </button>
                      ))}
                      {overflow > 0 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedKey(isSelected ? null : key);
                          }}
                          className="px-1 text-[10px] font-medium text-gray-400 hover:text-gray-600 text-left"
                        >
                          +{overflow} more
                        </button>
                      )}
                    </div>
                  </div>
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
                      <li
                        key={item.id}
                        className="flex items-start gap-2.5 cursor-pointer hover:bg-gray-50 rounded-md p-1 -m-1"
                        onClick={() => {
                          setSelectedKey(null);
                          openPanelForItem(item);
                        }}
                      >
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
                            <Link
                              href={`/dashboard/clients/${item.client_id}?tab=actions`}
                              className="text-xs font-medium text-blue-600 hover:underline"
                              onClick={(e) => e.stopPropagation()}
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

              {/* Empty state */}
              {(!selectedDayData || selectedDayData.actionItems.length === 0) && (
                <p className="px-4 py-6 text-center text-sm text-gray-400">
                  No items for this day.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── TaskDetailPanel ──────────────────────────────────────────────────── */}
      <TaskDetailPanel
        item={panelItem}
        isOpen={panelOpen}
        defaultDueDate={createDate ?? undefined}
        onClose={() => setPanelOpen(false)}
        onSaved={handlePanelSaved}
        onDeleted={handlePanelDeleted}
      />
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
