"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { ActionItem, DashboardSummary, TaskBoardItem } from "@/lib/api";
import { createActionItemsApi, createDashboardApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import TaskDetailPanel from "@/components/action-items/TaskDetailPanel";

/* ── Icons ────────────────────────────────────────────────────────────────── */

function ListChecksIcon() {
  return (
    <svg className="h-4 w-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 6h11" /><path d="M10 12h11" /><path d="M10 18h11" />
      <polyline points="3 6 4 7 6 5" /><polyline points="3 12 4 13 6 11" /><polyline points="3 18 4 19 6 17" />
    </svg>
  );
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-blue-500" />
    </div>
  );
}

/* ── Date helpers ─────────────────────────────────────────────────────────── */

function toLocal(iso: string): Date {
  return new Date(iso + "T00:00:00");
}

function todayDate(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatDate(iso: string): string {
  return toLocal(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function relativeDay(iso: string): string {
  const t = todayDate();
  const d = toLocal(iso);
  const diff = Math.round((d.getTime() - t.getTime()) / 86400000);
  if (diff === 1) return "Tomorrow";
  if (diff <= 6) return d.toLocaleDateString("en-US", { weekday: "short" });
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/* ── Group pending items ──────────────────────────────────────────────────── */

interface GroupedTasks {
  today: TaskBoardItem[];
  overdue: TaskBoardItem[];
  next: TaskBoardItem[];
  unscheduled: TaskBoardItem[];
}

function groupPending(items: TaskBoardItem[]): GroupedTasks {
  const t = todayDate();
  const weekOut = new Date(t);
  weekOut.setDate(weekOut.getDate() + 7);

  const today: TaskBoardItem[] = [];
  const overdue: TaskBoardItem[] = [];
  const next: TaskBoardItem[] = [];
  const unscheduled: TaskBoardItem[] = [];

  for (const item of items) {
    if (!item.due_date) {
      unscheduled.push(item);
      continue;
    }
    const d = toLocal(item.due_date);
    if (d < t) overdue.push(item);
    else if (d.getTime() === t.getTime()) today.push(item);
    else if (d <= weekOut) next.push(item);
    else next.push(item); // beyond 7 days still goes in "next" since the API limits results
  }

  return { today, overdue, next, unscheduled };
}

/* ── Collapsible section ──────────────────────────────────────────────────── */

type SectionKey = "today" | "overdue" | "next" | "unscheduled";

function TaskSection({
  label,
  count,
  bgClass,
  textClass,
  dotClass,
  badgeClass,
  items,
  maxItems,
  moreHref,
  moreTextClass,
  renderRight,
  emptyText,
  expanded,
  onToggle,
  onItemClick,
}: {
  label: string;
  count: number;
  bgClass: string;
  textClass: string;
  dotClass: string;
  badgeClass: string;
  items: TaskBoardItem[];
  maxItems: number;
  moreHref: string;
  moreTextClass: string;
  renderRight: (item: TaskBoardItem) => string;
  emptyText?: string;
  expanded: boolean;
  onToggle: () => void;
  onItemClick: (item: TaskBoardItem) => void;
}) {
  if (items.length === 0 && !emptyText) return null;

  return (
    <div>
      <button
        onClick={onToggle}
        className={`-mx-5 flex w-[calc(100%+40px)] items-center gap-1.5 px-5 py-1.5 text-left transition-colors hover:brightness-95 ${bgClass}`}
      >
        {expanded ? (
          <ChevronDown className={`h-3.5 w-3.5 ${textClass}`} />
        ) : (
          <ChevronRight className={`h-3.5 w-3.5 ${textClass}`} />
        )}
        <span className={`text-[11px] font-medium uppercase tracking-wide ${textClass}`}>
          {label} &middot; {count}
        </span>
      </button>

      {expanded && (
        <div className="transition-all duration-200">
          {items.length === 0 && emptyText ? (
            <p className="py-2.5 text-[12px] text-gray-400">{emptyText}</p>
          ) : (
            <div>
              {items.slice(0, maxItems).map((item) => (
                <div
                  key={item.id}
                  onClick={() => onItemClick(item)}
                  className="-mx-1 flex items-start gap-2 rounded px-1 py-2 transition-colors hover:bg-gray-50 cursor-pointer"
                >
                  <span className={`mt-[7px] inline-block h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-gray-900 line-clamp-1">{item.text}</p>
                    <p className="text-[11px] text-gray-400">
                      <Link
                        href={`/dashboard/clients/${item.client_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="hover:text-blue-500 hover:underline"
                      >
                        {item.client_name}
                      </Link>
                      {item.due_date ? ` \u00B7 Due ${formatDate(item.due_date)}` : " \u00B7 No due date"}
                    </p>
                  </div>
                  {renderRight(item) && (
                    <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeClass}`}>
                      {renderRight(item)}
                    </span>
                  )}
                </div>
              ))}
              {items.length > maxItems && (
                <Link
                  href={moreHref}
                  className={`block py-1 pl-4 text-[11px] ${moreTextClass} hover:underline`}
                >
                  +{items.length - maxItems} more
                </Link>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Tab types ────────────────────────────────────────────────────────────── */

type Tab = "todo" | "done" | "delegated";

/* ── Props ────────────────────────────────────────────────────────────────── */

interface Props {
  data: DashboardSummary;
}

/* ── Main component ───────────────────────────────────────────────────────── */

export default function TaskBoard({ data }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [activeTab, setActiveTab] = useState<Tab>("todo");

  // To Do data
  const [todoItems, setTodoItems] = useState<TaskBoardItem[] | null>(null);
  // Done data (lazy)
  const [doneItems, setDoneItems] = useState<TaskBoardItem[] | null>(null);
  const [doneLoaded, setDoneLoaded] = useState(false);

  // Collapsible state
  const [expanded, setExpanded] = useState<Record<SectionKey, boolean>>({
    today: true,
    overdue: false,
    next: false,
    unscheduled: false,
  });

  // Panel state
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelItem, setPanelItem] = useState<ActionItem | null>(null);

  const toggle = useCallback((key: SectionKey) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // Fetch To Do items
  const fetchTodo = useCallback(() => {
    const api = createDashboardApi(getToken, activeOrg?.id);
    api.taskBoardItems().then(setTodoItems).catch(() => {});
  }, [getToken, activeOrg]);

  useEffect(() => {
    fetchTodo();
  }, [fetchTodo]);

  // Lazy-fetch Done items when tab is clicked
  useEffect(() => {
    if (activeTab === "done" && !doneLoaded) {
      const api = createDashboardApi(getToken, activeOrg?.id);
      api.taskBoardCompleted(10).then((items) => {
        setDoneItems(items);
        setDoneLoaded(true);
      }).catch(() => setDoneLoaded(true));
    }
  }, [activeTab, doneLoaded, getToken, activeOrg]);

  const grouped = useMemo(() => {
    if (!todoItems) return null;
    return groupPending(todoItems);
  }, [todoItems]);

  const hasFirmOrg = data.team_members != null;

  const tabs: Array<{ key: Tab; label: string }> = [
    { key: "todo", label: "To Do" },
    { key: "done", label: "Done" },
    { key: "delegated", label: "Delegated" },
  ];

  // Convert TaskBoardItem to a partial ActionItem for immediate panel display
  function boardItemToActionItem(boardItem: TaskBoardItem): ActionItem {
    return {
      id: boardItem.id,
      document_id: null,
      client_id: boardItem.client_id,
      text: boardItem.text,
      status: boardItem.status,
      priority: null,
      due_date: boardItem.due_date,
      assigned_to: null,
      assigned_to_name: null,
      notes: null,
      source: "ai_extracted",
      engagement_task_id: null,
      created_by: null,
      extracted_at: null,
      completed_at: boardItem.completed_at,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      document_filename: null,
      client_name: boardItem.client_name,
    };
  }

  // Open panel immediately with partial data, then backfill full ActionItem
  function handleItemClick(boardItem: TaskBoardItem) {
    const partial = boardItemToActionItem(boardItem);
    setPanelItem(partial);
    setPanelOpen(true);
    // Fetch full data in background to populate priority, notes, assigned_to, etc.
    const api = createActionItemsApi(getToken, activeOrg?.id);
    api.list(boardItem.client_id, undefined, 0, 200).then((res) => {
      const full = res.items.find((i) => i.id === boardItem.id);
      if (full) setPanelItem(full);
    }).catch(() => { /* keep partial data — panel still works */ });
  }

  function closePanel() {
    setPanelOpen(false);
    setPanelItem(null);
  }

  function handlePanelSaved() {
    // Re-fetch todo items to reflect changes
    fetchTodo();
    setDoneLoaded(false);
  }

  function handlePanelDeleted() {
    fetchTodo();
    setDoneLoaded(false);
  }

  function openCreatePanel() {
    setPanelItem(null);
    setPanelOpen(true);
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-2">
        <div className="flex items-center gap-1.5">
          <ListChecksIcon />
          <h3 className="text-sm font-semibold text-gray-900">Tasks & deadlines</h3>
        </div>
        <Link href="/dashboard/actions" className="text-xs text-gray-500 hover:text-gray-700">
          View all &rarr;
        </Link>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-gray-100 px-5">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`pb-2 text-[12px] font-medium transition-colors ${
              activeTab === tab.key
                ? "border-b-2 border-blue-500 text-gray-900"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="relative min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-2">
        {/* ── To Do tab ── */}
        {activeTab === "todo" && (
          todoItems === null ? <Spinner /> : !grouped || (grouped.today.length === 0 && grouped.overdue.length === 0 && grouped.next.length === 0 && grouped.unscheduled.length === 0) ? (
            <div className="flex flex-col items-center justify-center py-8">
              <svg className="h-5 w-5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="mt-1.5 text-sm text-gray-500">All clear, no tasks</span>
              <button
                onClick={openCreatePanel}
                className="mt-2 text-[12px] text-blue-500 hover:text-blue-700 hover:underline"
              >
                + Add task
              </button>
            </div>
          ) : (
            <div className="space-y-1">
              {grouped.today.length === 0 ? (
                <div className="flex items-center gap-1.5 py-1">
                  <svg className="h-4 w-4 text-emerald-600/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-[12px] font-medium text-emerald-600/70">All clear for today</span>
                </div>
              ) : (
                <TaskSection
                  label="TODAY"
                  count={grouped.today.length}
                  bgClass="bg-blue-50"
                  textClass="text-blue-500"
                  dotClass="bg-blue-500"
                  badgeClass="bg-blue-50 text-blue-600"
                  items={grouped.today}
                  maxItems={5}
                  moreHref="/dashboard/actions?filter=today"
                  moreTextClass="text-blue-400"
                  renderRight={() => "Today"}
                  expanded={expanded.today}
                  onToggle={() => toggle("today")}
                  onItemClick={handleItemClick}
                />
              )}

              <TaskSection
                label="OVERDUE"
                count={grouped.overdue.length}
                bgClass="bg-red-50"
                textClass="text-red-500"
                dotClass="bg-red-500"
                badgeClass="bg-red-50 text-red-600"
                items={grouped.overdue}
                maxItems={5}
                moreHref="/dashboard/actions?filter=overdue"
                moreTextClass="text-red-400"
                renderRight={(item) => {
                  const d = item.overdue_days ?? Math.round((todayDate().getTime() - toLocal(item.due_date!).getTime()) / 86400000);
                  return `${d}d late`;
                }}
                expanded={expanded.overdue}
                onToggle={() => toggle("overdue")}
                onItemClick={handleItemClick}
              />

              <TaskSection
                label="NEXT"
                count={grouped.next.length}
                bgClass="bg-gray-50"
                textClass="text-gray-600"
                dotClass="bg-gray-400"
                badgeClass="bg-gray-50 text-gray-600"
                items={grouped.next}
                maxItems={5}
                moreHref="/dashboard/actions?filter=upcoming"
                moreTextClass="text-gray-400"
                renderRight={(item) => item.due_date ? relativeDay(item.due_date) : ""}
                emptyText="Clear schedule ahead"
                expanded={expanded.next}
                onToggle={() => toggle("next")}
                onItemClick={handleItemClick}
              />

              <TaskSection
                label="UNSCHEDULED"
                count={grouped.unscheduled.length}
                bgClass="bg-gray-50"
                textClass="text-gray-400"
                dotClass="bg-gray-300"
                badgeClass="bg-gray-50 text-gray-400"
                items={grouped.unscheduled}
                maxItems={5}
                moreHref="/dashboard/actions"
                moreTextClass="text-gray-400"
                renderRight={() => ""}
                expanded={expanded.unscheduled}
                onToggle={() => toggle("unscheduled")}
                onItemClick={handleItemClick}
              />

              {/* Add task link */}
              <button
                onClick={openCreatePanel}
                className="mt-2 block w-full py-1.5 text-center text-[11px] text-blue-400 hover:text-blue-600 hover:underline"
              >
                + Add task
              </button>
            </div>
          )
        )}

        {/* ── Done tab ── */}
        {activeTab === "done" && (
          !doneLoaded ? <Spinner /> : doneItems && doneItems.length > 0 ? (
            <div>
              {doneItems.map((item) => (
                <div
                  key={item.id}
                  onClick={() => handleItemClick(item)}
                  className="-mx-1 flex items-start gap-2 rounded px-1 py-2 transition-colors hover:bg-gray-50 cursor-pointer"
                >
                  <span className="mt-[7px] inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-green-500" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-gray-900 line-clamp-1">{item.text}</p>
                    <p className="text-[11px] text-gray-400">
                      {item.client_name}
                      {item.completed_at ? ` \u00B7 Completed ${relativeTime(item.completed_at)}` : ""}
                    </p>
                  </div>
                </div>
              ))}
              <Link
                href="/dashboard/actions?filter=completed"
                className="mt-1 block text-center text-[11px] text-gray-400 hover:text-gray-600 hover:underline"
              >
                View all &rarr;
              </Link>
            </div>
          ) : (
            <p className="py-8 text-center text-[13px] text-gray-400">No completed items yet</p>
          )
        )}

        {/* ── Delegated tab ── */}
        {activeTab === "delegated" && (
          hasFirmOrg ? (
            <p className="py-8 text-center text-[13px] text-gray-400">No delegated tasks</p>
          ) : (
            <div className="flex flex-col items-center py-8 text-center">
              <p className="text-[13px] text-gray-400">Delegated tasks appear here when you have team members</p>
              <Link
                href="/dashboard/settings/organization"
                className="mt-1.5 text-[12px] text-blue-500 hover:text-blue-700 hover:underline"
              >
                Organization settings &rarr;
              </Link>
            </div>
          )
        )}

        {/* Fade at bottom */}
        <div className="pointer-events-none sticky bottom-0 -mb-5 h-4 bg-gradient-to-t from-white to-transparent" />
      </div>

      {/* Task detail panel */}
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
