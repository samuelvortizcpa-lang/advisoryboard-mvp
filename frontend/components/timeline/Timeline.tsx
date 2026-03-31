"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import {
  ActionItemTimelineItem,
  CommunicationTimelineItem,
  DocumentTimelineItem,
  TimelineItem,
  createTimelineApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type FilterType = "all" | "document" | "action_item" | "communication";

interface TimelineProps {
  clientId: string;
  refreshKey?: number;
  onDocumentClick?: (id: string) => void;
  onActionItemClick?: (id: string) => void;
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

const GROUP_ORDER = ["Today", "Yesterday", "This Week", "This Month", "Older"];

function getDateGroup(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const weekStart = new Date(todayStart);
  weekStart.setDate(weekStart.getDate() - 7);
  const monthStart = new Date(todayStart);
  monthStart.setDate(monthStart.getDate() - 30);

  if (date >= todayStart) return "Today";
  if (date >= yesterdayStart) return "Yesterday";
  if (date >= weekStart) return "This Week";
  if (date >= monthStart) return "This Month";
  return "Older";
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatFullTimestamp(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function ClockIcon() {
  return (
    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg
      className="h-3 w-3"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      className="h-3 w-3"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
      />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  );
}

// ─── Badge sub-components ─────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700",
  completed: "bg-green-50 text-green-700",
  cancelled: "bg-gray-100 text-gray-500",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-500";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}
    >
      {status}
    </span>
  );
}

const PRIORITY_STYLES: Record<string, string> = {
  low: "bg-blue-50 text-blue-600",
  medium: "bg-orange-50 text-orange-600",
  high: "bg-red-50 text-red-600",
};

function PriorityBadge({ priority }: { priority: string }) {
  const cls = PRIORITY_STYLES[priority] ?? "bg-gray-100 text-gray-500";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}
    >
      {priority}
    </span>
  );
}

// ─── Item cards ───────────────────────────────────────────────────────────────

function DocumentCard({
  item,
  onClick,
}: {
  item: DocumentTimelineItem;
  onClick?: () => void;
}) {
  return (
    <button onClick={onClick} className="w-full text-left">
      <div className="rounded-lg border border-gray-200 px-3 py-2.5 transition hover:border-blue-200 hover:bg-blue-50/40">
        <p className="truncate text-sm font-medium text-gray-900">
          {item.filename}
        </p>
        <p className="mt-0.5 text-xs text-gray-500">
          <span className="font-medium uppercase">{item.file_type}</span>
          {" · "}
          {formatFileSize(item.file_size)}
          {item.processed && (
            <span className="ml-1.5 text-green-600">· Processed</span>
          )}
        </p>
      </div>
    </button>
  );
}

function ActionItemCard({
  item,
  onClick,
}: {
  item: ActionItemTimelineItem;
  onClick?: () => void;
}) {
  return (
    <button onClick={onClick} className="w-full text-left">
      <div className="rounded-lg border border-gray-200 px-3 py-2.5 transition hover:border-purple-200 hover:bg-purple-50/40">
        <p
          className={`text-sm text-gray-900 ${
            item.status === "completed" ? "line-through text-gray-400" : ""
          }`}
        >
          {item.text}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <StatusBadge status={item.status} />
          {item.priority && <PriorityBadge priority={item.priority} />}
          {item.source_doc && (
            <span className="max-w-[140px] truncate text-xs text-gray-400">
              {item.source_doc}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

function CommunicationCard({ item }: { item: CommunicationTimelineItem }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <button onClick={() => setExpanded(!expanded)} className="w-full text-left">
      <div className="rounded-lg border border-gray-200 px-3 py-2.5 transition hover:border-green-200 hover:bg-green-50/40">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-sm font-medium text-gray-900">{item.title}</p>
          {item.metadata?.ai_drafted && (
            <span className="inline-flex items-center rounded-full bg-purple-50 px-1.5 py-0.5 text-[10px] font-medium text-purple-700">
              AI
            </span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-gray-500">
          {item.subtitle}
          {item.metadata?.template_name && (
            <span className="ml-1.5 text-gray-400">
              · {item.metadata.template_name}
            </span>
          )}
        </p>
        {expanded && item.title && (
          <p className="mt-2 text-xs text-gray-400 leading-relaxed border-t border-gray-100 pt-2">
            Click to view full email in communications history
          </p>
        )}
      </div>
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Timeline({
  clientId,
  refreshKey = 0,
  onDocumentClick,
  onActionItemClick,
}: TimelineProps) {
  const { getToken } = useAuth();
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>("all");
  const [page, setPage] = useState(0);
  const [retryCount, setRetryCount] = useState(0);
  const LIMIT = 50;

  useEffect(() => {
    setLoading(true);
    setError(null);
    const types = filter === "all" ? undefined : [filter];
    createTimelineApi(getToken)
      .list(clientId, { types, limit: LIMIT, skip: page * LIMIT })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [clientId, getToken, filter, page, refreshKey, retryCount]);

  function handleFilterChange(f: FilterType) {
    setFilter(f);
    setPage(0);
  }

  // Build ordered groups
  const groupMap = new Map<string, TimelineItem[]>();
  for (const item of items) {
    const label = getDateGroup(item.date);
    if (!groupMap.has(label)) groupMap.set(label, []);
    groupMap.get(label)!.push(item);
  }
  const groups = GROUP_ORDER.filter((l) => groupMap.has(l)).map((l) => ({
    label: l,
    items: groupMap.get(l)!,
  }));

  const skip = page * LIMIT;
  const hasPrev = page > 0;
  const hasNext = skip + LIMIT < total;

  return (
    <div>
      {/* Header + filter chips */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-900">Timeline</h2>
        <div className="flex gap-1">
          {(
            [
              { value: "all" as FilterType, label: "All" },
              { value: "document" as FilterType, label: "Documents" },
              { value: "action_item" as FilterType, label: "Actions" },
              { value: "communication" as FilterType, label: "Emails" },
            ] as const
          ).map(({ value, label }) => (
            <button
              key={value}
              onClick={() => handleFilterChange(value)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                filter === value
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          Loading...
        </div>
      ) : error ? (
        <div className="flex items-center justify-between px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
          <span>{error}</span>
          <button onClick={() => setRetryCount(c => c + 1)} className="text-red-500 underline text-xs">Retry</button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
            <ClockIcon />
          </div>
          <p className="text-sm text-gray-500">No activity yet</p>
          <p className="mt-1 text-xs text-gray-400">Upload documents to start building a history.</p>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white px-4 py-4 shadow-sm">
            {groups.map((group, gi) => (
              <div key={group.label} className={gi > 0 ? "mt-5" : ""}>
                {/* Group label */}
                <div className="mb-3 flex items-center gap-3">
                  <div className="flex w-8 flex-shrink-0 justify-center">
                    <div className="h-3 w-3 rounded-full bg-gray-200 ring-2 ring-white" />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                    {group.label}
                  </span>
                </div>

                {/* Items with vertical line */}
                <div className="relative">
                  {/* Line runs through the dot column for this group */}
                  <div className="absolute left-4 top-0 bottom-3 w-px bg-gray-100" />

                  {group.items.map((item, ii) => (
                    <div
                      key={`${item.type}-${item.id}`}
                      className={`relative flex items-start gap-3 ${
                        ii < group.items.length - 1 ? "mb-4" : ""
                      }`}
                    >
                      {/* Colored dot with icon */}
                      <div className="flex w-8 flex-shrink-0 justify-center pt-0.5">
                        <div
                          className={`relative z-10 flex h-6 w-6 items-center justify-center rounded-full text-white ring-2 ring-white ${
                            item.type === "document"
                              ? "bg-blue-500"
                              : item.type === "communication"
                              ? "bg-green-500"
                              : "bg-purple-500"
                          }`}
                        >
                          {item.type === "document" ? (
                            <DocIcon />
                          ) : item.type === "communication" ? (
                            <MailIcon />
                          ) : (
                            <CheckIcon />
                          )}
                        </div>
                      </div>

                      {/* Content */}
                      <div className="min-w-0 flex-1 pb-1">
                        {/* Timestamp row */}
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="text-xs text-gray-400">
                            {item.type === "document"
                              ? "Document uploaded"
                              : item.type === "communication"
                              ? "Email sent"
                              : "Action item created"}
                          </span>
                          <span
                            className="flex-shrink-0 cursor-default text-xs text-gray-400"
                            title={formatFullTimestamp(item.date)}
                          >
                            {formatRelativeTime(item.date)}
                          </span>
                        </div>

                        {/* Card */}
                        {item.type === "document" ? (
                          <DocumentCard
                            item={item}
                            onClick={() => onDocumentClick?.(item.id)}
                          />
                        ) : item.type === "communication" ? (
                          <CommunicationCard item={item} />
                        ) : (
                          <ActionItemCard
                            item={item}
                            onClick={() => onActionItemClick?.(item.id)}
                          />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {total > LIMIT && (
            <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
              <span>
                {skip + 1}–{Math.min(skip + LIMIT, total)} of {total}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={!hasPrev}
                  onClick={() => setPage((p) => p - 1)}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  disabled={!hasNext}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
