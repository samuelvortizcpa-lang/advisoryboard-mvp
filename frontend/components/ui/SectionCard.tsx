import type { ReactNode } from "react";
import Link from "next/link";

export interface SectionCardProps {
  title: string;
  action?: { label: string; href: string };
  children: ReactNode;
}

export default function SectionCard({ title, action, children }: SectionCardProps) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        {action && (
          <Link
            href={action.href}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            {action.label}
          </Link>
        )}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}
