"use client";

import type { StrategyReference } from "@/lib/api";

interface StrategiesReferencedListProps {
  strategies: StrategyReference[];
}

export default function StrategiesReferencedList({ strategies }: StrategiesReferencedListProps) {
  if (strategies.length === 0) {
    return <p className="text-xs text-gray-400 italic">No strategies referenced.</p>;
  }

  return (
    <div>
      <p className="text-xs font-medium text-gray-500 mb-1.5">
        Strategies referenced ({strategies.length}):
      </p>
      <div className="flex flex-wrap gap-1.5">
        {strategies.map((s) => (
          <span
            key={s.id}
            className="inline-flex items-center rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 text-xs font-medium text-indigo-700"
          >
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}
