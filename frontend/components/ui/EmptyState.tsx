import type { ReactNode } from "react";
import Link from "next/link";

export interface EmptyStateProps {
  icon?: ReactNode;
  message: string;
  action?: { label: string; href: string };
}

export default function EmptyState({ icon, message, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center py-8">
      {icon && <div className="mb-3 text-gray-300">{icon}</div>}
      <p className="text-sm text-gray-500">{message}</p>
      {action && (
        <Link
          href={action.href}
          className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}
