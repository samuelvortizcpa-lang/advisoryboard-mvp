import Link from "next/link";
import type { ReactNode } from "react";

export interface StatCardProps {
  label: string;
  value: string | number;
  context?: string;
  contextType?: "success" | "warning" | "danger" | "muted";
  accentColor?: string;
  labelExtra?: ReactNode;
  href?: string;
}

const contextColors: Record<string, string> = {
  success: "text-green-600",
  warning: "text-amber-600",
  danger: "text-red-600",
  muted: "text-gray-400",
};

export default function StatCard({ label, value, context, contextType = "muted", accentColor: _accentColor, labelExtra, href }: StatCardProps) {
  const card = (
    <div className={`group relative rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md${href ? " cursor-pointer" : ""}`}>
      {href && (
        <svg
          className="absolute right-3 top-3 h-4 w-4 text-gray-300 opacity-0 transition-opacity duration-150 group-hover:opacity-100"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      )}
      <p className="flex items-center gap-1 text-xs text-gray-500">{label}{labelExtra}</p>
      <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
      {context && (
        <p className={`mt-1 text-xs ${contextColors[contextType]}`}>{context}</p>
      )}
    </div>
  );

  if (href) {
    return <Link href={href} className="block">{card}</Link>;
  }

  return card;
}
