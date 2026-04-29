"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

import type { ImplementationProgress, ImplementationTask } from "@/lib/api";
import { createActionItemsApi } from "@/lib/api";

interface ImplementationTaskListProps {
  progress: ImplementationProgress | null;
  loading: boolean;
  onTaskUpdated?: () => void;
}

const OWNER_COLORS: Record<string, string> = {
  cpa: "bg-blue-100 text-blue-700",
  client: "bg-orange-100 text-orange-700",
  third_party: "bg-purple-100 text-purple-700",
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function ownerLabel(task: ImplementationTask): string {
  if (task.owner_role === "third_party" && task.owner_external_label) {
    return task.owner_external_label;
  }
  if (task.owner_role === "third_party") return "Third-party";
  if (task.owner_role === "cpa") return "CPA";
  return "Client";
}

export default function ImplementationTaskList({
  progress,
  loading,
  onTaskUpdated,
}: ImplementationTaskListProps) {
  const { getToken } = useAuth();
  const [optimisticIds, setOptimisticIds] = useState<Set<string>>(new Set());
  const [errorId, setErrorId] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="px-5 py-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="mb-2 h-8 animate-pulse rounded bg-gray-50" />
        ))}
      </div>
    );
  }

  if (!progress || progress.total === 0) {
    return (
      <div className="px-5 py-3 text-xs text-gray-400">
        No implementation tasks yet. Tasks will be generated when this strategy moves to &lsquo;recommended&rsquo;.
      </div>
    );
  }

  async function markComplete(task: ImplementationTask) {
    setOptimisticIds((prev) => new Set(prev).add(task.id));
    setErrorId(null);
    try {
      const api = createActionItemsApi(getToken);
      await api.update(task.id, { status: "completed" });
      onTaskUpdated?.();
    } catch {
      setOptimisticIds((prev) => {
        const next = new Set(prev);
        next.delete(task.id);
        return next;
      });
      setErrorId(task.id);
      setTimeout(() => setErrorId(null), 3000);
    }
  }

  // TODO(G2-P4-followup): bulk operations (mark all complete, etc.)
  // TODO(G2-P4-followup): reassigning tasks to different CPAs
  // TODO(G2-P4-followup): editing due dates inline
  // TODO(G2-P4-followup): archive controls (POST .../implementation-tasks/archive)
  // TODO(G2-P4-followup): document-upload integration for required_documents

  return (
    <div className="border-l-2 border-blue-100 ml-5 mr-5 mb-3">
      {progress.tasks.map((task) => {
        const isOptimistic = optimisticIds.has(task.id);
        const isCompleted = task.status === "completed" || isOptimistic;
        const isCancelled = task.status === "cancelled";
        const canMarkComplete = task.status === "pending" && task.owner_role === "cpa" && !isOptimistic;

        return (
          <div
            key={task.id}
            className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-gray-50/50"
          >
            {/* Status icon */}
            {isCancelled ? (
              <span className="h-3.5 w-3.5 shrink-0 text-gray-300">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </span>
            ) : isCompleted ? (
              <span className="h-3.5 w-3.5 shrink-0 text-green-500">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </span>
            ) : (
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300 ml-0.5 mr-0.5" />
            )}

            {/* Task name */}
            <span className={`flex-1 min-w-0 ${isCancelled ? "line-through text-gray-400" : isCompleted ? "text-gray-500" : "text-gray-700"}`}>
              {task.task_name}
            </span>

            {/* Owner badge */}
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${OWNER_COLORS[task.owner_role] ?? OWNER_COLORS.third_party}`}>
              {ownerLabel(task)}
            </span>

            {/* Due date */}
            {task.due_date && (
              <span className="shrink-0 text-[11px] text-gray-400">
                {formatDate(task.due_date)}
              </span>
            )}

            {/* Mark complete button */}
            {canMarkComplete && (
              <button
                type="button"
                onClick={() => markComplete(task)}
                className="shrink-0 rounded border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 hover:bg-green-50 hover:border-green-200 hover:text-green-600 transition-colors"
              >
                Done
              </button>
            )}

            {/* Error indicator */}
            {errorId === task.id && (
              <span className="shrink-0 text-[10px] text-red-500">Failed</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
