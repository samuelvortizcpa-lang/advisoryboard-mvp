export interface StatCardProps {
  label: string;
  value: string | number;
  context?: string;
  contextType?: "success" | "warning" | "danger" | "muted";
}

const contextColors: Record<string, string> = {
  success: "text-green-600",
  warning: "text-amber-600",
  danger: "text-red-600",
  muted: "text-gray-400",
};

export default function StatCard({ label, value, context, contextType = "muted" }: StatCardProps) {
  return (
    <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-900">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
      {context && (
        <p className={`mt-1 text-xs ${contextColors[contextType]}`}>{context}</p>
      )}
    </div>
  );
}
