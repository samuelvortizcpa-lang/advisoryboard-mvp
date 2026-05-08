"use client";

import type { TaskReference } from "@/lib/api";

interface ClientFacingTasksListProps {
  tasks: TaskReference[];
}

export default function ClientFacingTasksList({ tasks }: ClientFacingTasksListProps) {
  if (tasks.length === 0) {
    return <p className="text-xs text-gray-400 italic">No client-facing tasks referenced.</p>;
  }

  return (
    <div>
      <p className="text-xs font-medium text-gray-500 mb-1.5">
        Client-facing tasks ({tasks.length}):
      </p>
      <div className="flex flex-col gap-1.5">
        {tasks.map((t) => (
          <div
            key={t.id}
            className="flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs"
          >
            <span className="font-medium text-gray-800">{t.name}</span>
            <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 uppercase">
              {t.owner_role}
            </span>
            <span className="text-gray-400">{t.due_date ?? "—"}</span>
            {t.strategy_name && (
              <span className="text-gray-400 italic">{t.strategy_name}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
