"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ImplementationProgress as ProgressData } from "@/lib/api";

interface ImplementationProgressProps {
  progress: ProgressData | null;
  loading: boolean;
  status: string;
  onClick?: () => void;
}

const HIDDEN_STATUSES = new Set(["not_reviewed", "declined", "not_applicable"]);

export default function ImplementationProgress({
  progress,
  loading,
  status,
  onClick,
}: ImplementationProgressProps) {
  const [tooltipVisible, setTooltipVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  if (HIDDEN_STATUSES.has(status)) return null;

  if (loading || !progress) {
    return (
      <span className="inline-block h-5 w-12 animate-pulse rounded-full bg-gray-100" />
    );
  }

  if (progress.total === 0) {
    return (
      <span className="text-[11px] text-gray-400">0 tasks</span>
    );
  }

  const { completed, total, by_owner_role } = progress;

  let pillColor = "bg-gray-100 text-gray-600";
  if (completed === total) pillColor = "bg-green-100 text-green-700";
  else if (completed > 0) pillColor = "bg-blue-100 text-blue-700";

  // Build tooltip text from role breakdown
  const roleLabels: Array<[string, string]> = [
    ["cpa", "CPA"],
    ["client", "Client"],
    ["third_party", "Third-party"],
  ];
  const tooltipParts = roleLabels
    .map(([key, label]) => {
      const bd = by_owner_role[key as keyof typeof by_owner_role];
      if (!bd || bd.total === 0) return null;
      return `${label}: ${bd.completed}/${bd.total}`;
    })
    .filter(Boolean);
  const tooltipText = tooltipParts.join(" · ");

  function showTip() {
    timerRef.current = setTimeout(() => setTooltipVisible(true), 200);
  }
  function hideTip() {
    if (timerRef.current) clearTimeout(timerRef.current);
    setTooltipVisible(false);
  }

  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={showTip}
      onMouseLeave={hideTip}
    >
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${pillColor} cursor-pointer transition-opacity hover:opacity-80`}
      >
        {completed} / {total}
      </button>
      {tooltipVisible && tooltipText && (
        <span className="absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 pointer-events-none">
          <span className="block whitespace-nowrap rounded-md bg-gray-900 px-3 py-1.5 text-[11px] text-white shadow-lg">
            {tooltipText}
          </span>
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-t-gray-900 border-x-transparent border-b-transparent h-0 w-0" />
        </span>
      )}
    </span>
  );
}
