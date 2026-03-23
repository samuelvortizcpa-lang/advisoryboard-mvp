export interface PriorityDotProps {
  priority: "critical" | "warning" | "info" | "success";
}

const dotColors: Record<PriorityDotProps["priority"], string> = {
  critical: "bg-red-500",
  warning: "bg-amber-500",
  info: "bg-blue-500",
  success: "bg-green-500",
};

export default function PriorityDot({ priority }: PriorityDotProps) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${dotColors[priority]}`}
    />
  );
}
