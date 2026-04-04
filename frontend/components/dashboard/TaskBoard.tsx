"use client";

import Link from "next/link";
import { useMemo } from "react";

import type { DeadlineItem } from "@/lib/api";

interface Props {
  items: DeadlineItem[] | null;
}

/* ── ListChecks icon (lucide) ─────────────────────────────────────────────── */
function ListChecksIcon() {
  return (
    <svg className="h-4 w-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 6h11" />
      <path d="M10 12h11" />
      <path d="M10 18h11" />
      <polyline points="3 6 4 7 6 5" />
      <polyline points="3 12 4 13 6 11" />
      <polyline points="3 18 4 19 6 17" />
    </svg>
  );
}

/* ── Date helpers ─────────────────────────────────────────────────────────── */

function toLocalDate(iso: string): Date {
  return new Date(iso + "T00:00:00");
}

function today(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatDate(iso: string): string {
  return toLocalDate(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function relativeDay(iso: string): string {
  const t = today();
  const d = toLocalDate(iso);
  const diff = Math.round((d.getTime() - t.getTime()) / 86400000);
  if (diff === 1) return "Tomorrow";
  if (diff <= 6) return d.toLocaleDateString("en-US", { weekday: "short" });
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/* ── Group items into overdue / today / upcoming ──────────────────────────── */

interface GroupedTasks {
  overdue: DeadlineItem[];
  dueToday: DeadlineItem[];
  upcoming: DeadlineItem[];
}

function groupTasks(items: DeadlineItem[]): GroupedTasks {
  const t = today();
  const overdue: DeadlineItem[] = [];
  const dueToday: DeadlineItem[] = [];
  const upcoming: DeadlineItem[] = [];

  for (const item of items) {
    const d = toLocalDate(item.due_date);
    if (d < t) overdue.push(item);
    else if (d.getTime() === t.getTime()) dueToday.push(item);
    else upcoming.push(item);
  }

  return { overdue, dueToday, upcoming };
}

/* ── Section component ────────────────────────────────────────────────────── */

function TaskSection({
  label,
  count,
  color,
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
}: {
  label: string;
  count: number;
  color: string;
  bgClass: string;
  textClass: string;
  dotClass: string;
  badgeClass: string;
  items: DeadlineItem[];
  maxItems: number;
  moreHref: string;
  moreTextClass: string;
  renderRight: (item: DeadlineItem) => string;
  emptyText?: string;
}) {
  // If no items and no emptyText, don't render the section at all
  if (items.length === 0 && !emptyText) return null;

  return (
    <div>
      {/* Section header */}
      <div className={`-mx-5 flex items-center gap-2 px-5 py-1.5 ${bgClass}`}>
        <span className={`text-[11px] font-medium uppercase tracking-wide ${textClass}`}>
          {label} &middot; {count}
        </span>
      </div>

      {/* Items or empty state */}
      {items.length === 0 && emptyText ? (
        <p className="py-2.5 text-[12px] text-gray-400">{emptyText}</p>
      ) : (
        <div>
          {items.slice(0, maxItems).map((item) => (
            <Link
              key={item.id}
              href={`/dashboard/clients/${item.client_id}`}
              className="-mx-1 flex items-start gap-2 rounded px-1 py-2 transition-colors hover:bg-gray-50"
            >
              <span className={`mt-[7px] inline-block h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-gray-900">{item.text}</p>
                <p className="text-[11px] text-gray-400">
                  {item.client_name} &middot; Due {formatDate(item.due_date)}
                </p>
              </div>
              <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${badgeClass}`}>
                {renderRight(item)}
              </span>
            </Link>
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
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */

export default function TaskBoard({ items }: Props) {
  const loading = items === null;

  const grouped = useMemo(() => {
    if (!items) return null;
    return groupTasks(items);
  }, [items]);

  return (
    <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <div className="flex items-center gap-1.5">
          <ListChecksIcon />
          <h3 className="text-sm font-semibold text-gray-900">Tasks & deadlines</h3>
        </div>
        <Link href="/dashboard/action-items" className="text-xs text-gray-500 hover:text-gray-700">
          View all &rarr;
        </Link>
      </div>

      {/* Body */}
      <div className="relative min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-5 w-full rounded bg-gray-100" />
                <div className="mt-2 h-10 rounded bg-gray-50" />
              </div>
            ))}
          </div>
        ) : !grouped || (grouped.overdue.length === 0 && grouped.dueToday.length === 0 && grouped.upcoming.length === 0) ? (
          <div className="flex flex-col items-center justify-center py-10">
            <svg className="h-5 w-5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="mt-1.5 text-sm text-gray-500">All clear, no deadlines</span>
          </div>
        ) : (
          <div className="space-y-2">
            <TaskSection
              label="OVERDUE"
              count={grouped.overdue.length}
              color="red"
              bgClass="bg-red-50"
              textClass="text-red-500"
              dotClass="bg-red-500"
              badgeClass="bg-red-50 text-red-600"
              items={grouped.overdue}
              maxItems={3}
              moreHref="/dashboard/action-items?filter=overdue"
              moreTextClass="text-red-400"
              renderRight={(item) => {
                const d = item.overdue_days ?? Math.round((today().getTime() - toLocalDate(item.due_date).getTime()) / 86400000);
                return `${d}d late`;
              }}
            />

            <TaskSection
              label="DUE TODAY"
              count={grouped.dueToday.length}
              color="amber"
              bgClass="bg-amber-50"
              textClass="text-amber-600"
              dotClass="bg-amber-500"
              badgeClass="bg-amber-50 text-amber-600"
              items={grouped.dueToday}
              maxItems={3}
              moreHref="/dashboard/action-items?filter=today"
              moreTextClass="text-amber-500"
              renderRight={() => "Today"}
              emptyText="Nothing due today"
            />

            <TaskSection
              label="UPCOMING"
              count={grouped.upcoming.length}
              color="blue"
              bgClass="bg-blue-50"
              textClass="text-blue-500"
              dotClass="bg-blue-500"
              badgeClass="bg-blue-50 text-blue-600"
              items={grouped.upcoming}
              maxItems={3}
              moreHref="/dashboard/action-items?filter=upcoming"
              moreTextClass="text-blue-400"
              renderRight={(item) => relativeDay(item.due_date)}
              emptyText="Clear schedule ahead"
            />
          </div>
        )}

        {/* Fade gradient at bottom if content overflows */}
        <div className="pointer-events-none sticky bottom-0 -mb-5 h-4 bg-gradient-to-t from-white to-transparent" />
      </div>
    </div>
  );
}
