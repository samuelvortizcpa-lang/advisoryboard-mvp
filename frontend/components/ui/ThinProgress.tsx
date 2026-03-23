export interface ThinProgressProps {
  label: string;
  current: number;
  max: number;
  showLabel?: boolean;
}

export default function ThinProgress({ label, current, max, showLabel = true }: ThinProgressProps) {
  const pct = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  const fillColor = pct > 80 ? "bg-red-500" : pct >= 60 ? "bg-amber-500" : "bg-green-500";

  return (
    <div>
      {showLabel && (
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs text-gray-500">{label}</span>
          <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
            {current} / {max}
          </span>
        </div>
      )}
      <div className="h-1 w-full rounded-full bg-gray-200 dark:bg-gray-700">
        <div
          className={`h-1 rounded-full ${fillColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
