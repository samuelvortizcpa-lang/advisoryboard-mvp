"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import {
  CheckinResponse,
  CheckinDetail,
  createCheckinsApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CheckinHistoryProps {
  clientId: string;
  refreshKey?: number;
  onSendClick?: () => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function CheckinHistory({
  clientId,
  refreshKey = 0,
  onSendClick,
}: CheckinHistoryProps) {
  const { getToken } = useAuth();
  const [checkins, setCheckins] = useState<CheckinResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CheckinDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    createCheckinsApi(getToken)
      .getClientCheckins(clientId)
      .then((data) => {
        if (!cancelled) setCheckins(data);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [getToken, clientId, refreshKey]);

  function toggleExpand(checkin: CheckinResponse) {
    if (expandedId === checkin.id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }

    if (checkin.status !== "completed") {
      setExpandedId(checkin.id);
      setDetail(null);
      return;
    }

    setExpandedId(checkin.id);
    setDetailLoading(true);
    createCheckinsApi(getToken)
      .getCheckinDetail(checkin.id)
      .then((d) => setDetail(d))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="block h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
        <span className="ml-2 text-sm text-gray-500">Loading check-ins...</span>
      </div>
    );
  }

  if (checkins.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
          <ClipboardCheckIcon className="h-6 w-6 text-gray-400" />
        </div>
        <h3 className="text-sm font-semibold text-gray-900">No check-ins sent yet</h3>
        <p className="mt-1 text-sm text-gray-500">
          Send one to capture client context before your next meeting.
        </p>
        {onSendClick && (
          <button
            onClick={onSendClick}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#5bb8af] px-4 py-2 text-sm font-medium text-white hover:bg-[#4a9e96]"
          >
            <ClipboardCheckIcon className="h-4 w-4" />
            Send Check-in
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {checkins.map((ci) => (
        <div key={ci.id}>
          <button
            onClick={() => toggleExpand(ci)}
            className={`w-full rounded-xl border bg-white p-4 text-left transition-all hover:shadow-md ${
              expandedId === ci.id ? "border-[#5bb8af] shadow-md" : "border-gray-200"
            }`}
          >
            <div className="flex items-start justify-between">
              <div>
                <h4 className="text-sm font-semibold text-gray-900">{ci.template_name}</h4>
                <p className="mt-0.5 text-xs text-gray-500">
                  Sent {relativeDate(ci.sent_at)}
                  {ci.sent_to_name && ` to ${ci.sent_to_name}`}
                </p>
              </div>
              <StatusBadge status={ci.status} />
            </div>
            {ci.status === "completed" && ci.completed_at && (
              <p className="mt-1 text-xs text-gray-400">
                Completed {relativeDate(ci.completed_at)}
              </p>
            )}
          </button>

          {/* Expanded Q&A */}
          {expandedId === ci.id && (
            <div className="mt-1 rounded-b-xl border border-t-0 border-gray-200 bg-gray-50 px-5 py-4">
              {ci.status !== "completed" ? (
                <p className="text-sm text-gray-500">
                  {ci.status === "pending"
                    ? "Waiting for client response..."
                    : "This check-in has expired."}
                </p>
              ) : detailLoading ? (
                <div className="flex items-center gap-2 py-4">
                  <span className="block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
                  <span className="text-sm text-gray-500">Loading responses...</span>
                </div>
              ) : detail ? (
                <div className="space-y-4">
                  {detail.questions.map((q) => (
                    <div key={q.id}>
                      <p className="text-xs font-medium text-gray-500">{q.text}</p>
                      <div className="mt-1">
                        {q.type === "rating" ? (
                          <RatingDisplay value={q.answer as number} />
                        ) : q.type === "multiselect" && Array.isArray(q.answer) ? (
                          <div className="flex flex-wrap gap-1">
                            {(q.answer as string[]).map((tag) => (
                              <span
                                key={tag}
                                className="rounded-full bg-[#5bb8af]/10 px-2.5 py-0.5 text-xs font-medium text-[#5bb8af]"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="text-sm text-gray-900">
                            {q.answer != null ? String(q.answer) : "No answer"}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">Could not load responses.</p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Rating Display ─────────────────────────────────────────────────────────

function RatingDisplay({ value }: { value: number }) {
  const rating = typeof value === "number" ? Math.min(5, Math.max(0, Math.round(value))) : 0;
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`text-base ${i <= rating ? "text-amber-400" : "text-gray-300"}`}>
          {i <= rating ? "\u2605" : "\u2606"}
        </span>
      ))}
    </div>
  );
}

// ─── Status Badge ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-amber-50 text-amber-700",
    completed: "bg-teal-50 text-teal-700",
    expired: "bg-gray-100 text-gray-500",
  };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status] ?? styles.expired}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

// ─── Relative Date ──────────────────────────────────────────────────────────

function relativeDate(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) > 1 ? "s" : ""} ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ─── Icons ──────────────────────────────────────────────────────────────────

function ClipboardCheckIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.35 3.836c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15a2.25 2.25 0 011.65 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m8.9-4.414c.376.023.75.05 1.124.08 1.131.094 1.976 1.057 1.976 2.192V16.5A2.25 2.25 0 0118 18.75h-2.25m-7.5-10.5H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V18.75m-7.5-10.5h6.375c.621 0 1.125.504 1.125 1.125v9.375m-8.25-3l1.5 1.5 3-3.75" />
    </svg>
  );
}
