"use client";

import Link from "next/link";

import type { DeadlineItem } from "@/lib/api";

interface Props {
  items: DeadlineItem[] | null;
}

function priorityColor(priority: string): string {
  if (priority === "critical") return "bg-red-500";
  if (priority === "warning") return "bg-amber-500";
  return "bg-blue-500";
}

function formatDueLabel(dueDate: string, overdueDays: number | null): string {
  if (overdueDays != null && overdueDays > 0) {
    return `Overdue by ${overdueDays} day${overdueDays !== 1 ? "s" : ""}`;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  const diff = Math.round((due.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "Due today";
  if (diff === 1) return "Due tomorrow";
  return `Due in ${diff} days`;
}

function groupByDay(items: DeadlineItem[]): Map<string, DeadlineItem[]> {
  const groups = new Map<string, DeadlineItem[]>();

  // Overdue items get their own group
  const overdue = items.filter((i) => i.overdue_days != null && i.overdue_days > 0);
  const upcoming = items.filter((i) => !(i.overdue_days != null && i.overdue_days > 0));

  if (overdue.length > 0) {
    groups.set("Overdue", overdue);
  }

  for (const item of upcoming) {
    const d = new Date(item.due_date + "T00:00:00");
    const label = d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
    const existing = groups.get(label) ?? [];
    existing.push(item);
    groups.set(label, existing);
  }

  return groups;
}

export default function DeadlineTimeline({ items }: Props) {
  const loading = items === null;
  const empty = items !== null && items.length === 0;

  return (
    <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">Upcoming deadlines</h3>
        <Link href="/dashboard/actions" className="text-xs text-gray-500 hover:text-gray-700">
          View all &rarr;
        </Link>
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-3 w-20 rounded bg-gray-200" />
                <div className="mt-2 h-8 rounded bg-gray-100" />
              </div>
            ))}
          </div>
        ) : empty ? (
          <div className="flex flex-col items-center justify-center py-8">
            <svg className="h-5 w-5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="mt-1.5 text-sm text-gray-500">No upcoming deadlines</span>
          </div>
        ) : (
          <div className="space-y-3">
            {Array.from(groupByDay(items!)).map(([dayLabel, dayItems]) => (
              <div key={dayLabel}>
                <p className={`text-[11px] font-medium uppercase tracking-wide ${dayLabel === "Overdue" ? "text-red-600" : "text-gray-400"}`}>
                  {dayLabel}
                </p>
                <div className="mt-1 space-y-1">
                  {dayItems.slice(0, 3).map((item) => (
                    <Link
                      key={item.id}
                      href={`/dashboard/clients/${item.client_id}?tab=actions`}
                      className="-mx-1 flex items-start gap-2 rounded px-1 py-1.5 hover:bg-gray-50"
                    >
                      <span className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${priorityColor(item.priority)}`} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] text-gray-900">{item.text}</p>
                        <p className="text-[11px] text-gray-500">
                          {item.client_name} — {formatDueLabel(item.due_date, item.overdue_days)}
                        </p>
                      </div>
                    </Link>
                  ))}
                  {dayItems.length > 3 && (
                    <p className="pl-4 text-[11px] text-gray-400">+{dayItems.length - 3} more</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
