"use client";

import type { DeliverableKey } from "@/lib/api";
import { DELIVERABLE_KEYS, DELIVERABLE_LABELS } from "@/lib/api";

interface DeliverableTogglesGridProps {
  effectiveFlags: Record<DeliverableKey, boolean>;
  overrides: Partial<Record<DeliverableKey, boolean>>;
  isAdmin: boolean;
  onToggle: (key: DeliverableKey, newValue: boolean) => void;
  onResetAll: () => void;
}

export default function DeliverableTogglesGrid({
  effectiveFlags,
  overrides,
  isAdmin,
  onToggle,
  onResetAll,
}: DeliverableTogglesGridProps) {
  const overrideCount = Object.keys(overrides).length;

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-5 py-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
            Deliverables
          </p>
          {overrideCount > 0 && (
            <button
              onClick={onResetAll}
              disabled={!isAdmin}
              className="text-xs font-medium text-blue-600 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Reset all
            </button>
          )}
        </div>
      </div>

      <div className="divide-y divide-gray-50">
        {DELIVERABLE_KEYS.map((key) => {
          const enabled = effectiveFlags[key];
          const isOverride = key in overrides;
          return (
            <label
              key={key}
              className="flex items-center justify-between px-5 py-3 hover:bg-gray-50"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-700">
                  {DELIVERABLE_LABELS[key]}
                </span>
                {isOverride && (
                  <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-600">
                    override
                  </span>
                )}
              </div>
              <input
                type="checkbox"
                checked={enabled}
                disabled={!isAdmin}
                onChange={() => onToggle(key, !enabled)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </label>
          );
        })}
      </div>

      <div className="border-t border-gray-100 px-5 py-3">
        <p className="text-xs text-gray-400">
          {overrideCount > 0
            ? `${overrideCount} of 7 currently overridden`
            : "All deliverables follow template defaults"}
        </p>
      </div>
    </div>
  );
}
