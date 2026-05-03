"use client";

import type { ClientCadenceResponse } from "@/lib/api";

interface ActiveCadenceCardProps {
  cadence: ClientCadenceResponse;
  isAdmin: boolean;
  onChangeClick: () => void;
}

export default function ActiveCadenceCard({
  cadence,
  isAdmin,
  onChangeClick,
}: ActiveCadenceCardProps) {
  const enabledCount = Object.values(cadence.effective_flags).filter(Boolean).length;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-900">
              {cadence.template_name}
            </h3>
            <span
              className={[
                "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                cadence.template_is_system
                  ? "bg-purple-50 text-purple-700"
                  : "bg-blue-50 text-blue-700",
              ].join(" ")}
            >
              {cadence.template_is_system ? "System" : "Custom"}
            </span>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {enabledCount} of 7 deliverables enabled
          </p>
        </div>
        <div className="relative">
          <button
            onClick={onChangeClick}
            disabled={!isAdmin}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Change
          </button>
          {!isAdmin && (
            <span className="absolute -bottom-5 right-0 whitespace-nowrap text-[10px] text-gray-400">
              Admin only
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
