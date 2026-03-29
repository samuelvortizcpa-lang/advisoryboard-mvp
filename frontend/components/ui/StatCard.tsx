export interface StatCardProps {
  label: string;
  value: string | number;
  context?: string;
  contextType?: "success" | "warning" | "danger" | "muted";
  accentColor?: string;
}

const contextColors: Record<string, string> = {
  success: "text-green-600",
  warning: "text-amber-600",
  danger: "text-red-600",
  muted: "text-gray-400",
};

export default function StatCard({ label, value, context, contextType = "muted", accentColor }: StatCardProps) {
  return (
    <div className={`rounded-xl border border-gray-100 bg-white p-4 shadow-sm transition-shadow hover:shadow-md${accentColor ? ` border-l-4 ${accentColor}` : ""}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
      {context && (
        <p className={`mt-1 text-xs ${contextColors[contextType]}`}>{context}</p>
      )}
    </div>
  );
}
