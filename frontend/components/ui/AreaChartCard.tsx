"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

export interface AreaChartCardProps {
  title: string;
  subtitle?: string;
  data: Array<{ date: string; value: number }>;
  timeRange: "7d" | "30d" | "90d";
  onTimeRangeChange: (range: "7d" | "30d" | "90d") => void;
  color?: string;
  valueFormatter?: (value: number) => string;
  height?: number;
}

const TIME_RANGES: Array<"7d" | "30d" | "90d"> = ["7d", "30d", "90d"];

const COLOR_MAP: Record<string, { stroke: string; fill: string }> = {
  blue: { stroke: "#3b82f6", fill: "#3b82f6" },
  green: { stroke: "#22c55e", fill: "#22c55e" },
  purple: { stroke: "#a855f7", fill: "#a855f7" },
  amber: { stroke: "#f59e0b", fill: "#f59e0b" },
  red: { stroke: "#ef4444", fill: "#ef4444" },
};

function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function CustomTooltip({
  active,
  payload,
  label,
  valueFormatter,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
  valueFormatter: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-sm">
      <p className="text-xs text-gray-500">{label ? formatShortDate(label) : ""}</p>
      <p className="text-xs font-medium text-gray-900">
        {valueFormatter(payload[0].value)}
      </p>
    </div>
  );
}

export default function AreaChartCard({
  title,
  subtitle,
  data,
  timeRange,
  onTimeRangeChange,
  color = "blue",
  valueFormatter = (v) => String(v),
  height = 240,
}: AreaChartCardProps) {
  const colors = COLOR_MAP[color] ?? COLOR_MAP.blue;
  const gradientId = `area-gradient-${color}`;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
          {subtitle && (
            <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>
          )}
        </div>
        <div className="flex gap-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r}
              onClick={() => onTimeRangeChange(r)}
              className={`rounded-md px-2 py-1 text-xs transition-colors ${
                r === timeRange
                  ? "bg-gray-100 font-medium text-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="mt-4" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colors.fill} stopOpacity={0.2} />
                <stop offset="100%" stopColor={colors.fill} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#f3f4f6"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={formatShortDate}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip
              content={<CustomTooltip valueFormatter={valueFormatter} />}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={colors.stroke}
              strokeWidth={1.5}
              fill={`url(#${gradientId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
