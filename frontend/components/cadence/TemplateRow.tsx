"use client";

import Link from "next/link";

import type { CadenceTemplateSummary } from "@/lib/api";

interface TemplateRowProps {
  template: CadenceTemplateSummary;
  href: string;
}

export default function TemplateRow({ template, href }: TemplateRowProps) {
  return (
    <Link
      href={href}
      className={`flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 transition-colors hover:bg-gray-50 ${
        !template.is_active ? "opacity-60" : ""
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900 truncate">
            {template.name}
          </span>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              template.is_system
                ? "bg-purple-50 text-purple-700"
                : "bg-blue-50 text-blue-700"
            }`}
          >
            {template.is_system ? "System" : "Custom"}
          </span>
          {!template.is_active && (
            <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
              Inactive
            </span>
          )}
        </div>
        {template.description && (
          <p className="mt-0.5 text-xs text-gray-500 truncate">
            {template.description}
          </p>
        )}
      </div>
      <svg
        className="ml-3 h-4 w-4 shrink-0 text-gray-400"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M8.25 4.5l7.5 7.5-7.5 7.5"
        />
      </svg>
    </Link>
  );
}
