"use client";

import type { ReactNode } from "react";
import { ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

export interface DonutChartItem {
  name: string;
  value: number;
  color: string;
}

export interface DonutChartCardProps {
  title: string;
  data: DonutChartItem[];
  centerLabel?: string;
  centerValue?: string | number;
  height?: number;
  titleExtra?: ReactNode;
}

export default function DonutChartCard({
  title,
  data,
  centerLabel,
  centerValue,
  height = 240,
  titleExtra,
}: DonutChartCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      <h3 className="flex items-center gap-1 text-sm font-semibold text-gray-900">{title}{titleExtra}</h3>

      {/* Chart with center label */}
      <div className="relative mt-3" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={2}
              stroke="none"
            >
              {data.map((item, i) => (
                <Cell key={i} fill={item.color} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>

        {/* Center text */}
        {(centerValue !== undefined || centerLabel) && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            {centerValue !== undefined && (
              <span className="text-xl font-semibold text-gray-900">
                {centerValue}
              </span>
            )}
            {centerLabel && (
              <span className="text-xs text-gray-500">{centerLabel}</span>
            )}
          </div>
        )}
      </div>

      {/* Custom legend */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {data.map((item, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-xs text-gray-600">{item.name}</span>
            <span className="text-xs font-medium text-gray-900">
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
