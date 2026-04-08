"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import type { EngagementTemplate } from "@/lib/api";
import { createEngagementsApi } from "@/lib/api";

export default function EngagementsPage() {
  const { getToken } = useAuth();
  const [templates, setTemplates] = useState<EngagementTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    createEngagementsApi(getToken)
      .listTemplates()
      .then((data) => {
        if (!cancelled) setTemplates(data);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [getToken]);

  const activeTemplates = templates.filter((t) => t.is_active);

  return (
    <div className="px-8 py-8 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
            Workflows
          </p>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">Engagements</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage recurring engagement templates and client assignments.
          </p>
        </div>
        <Link
          href="/dashboard/settings/engagements"
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
        >
          Manage templates in Settings →
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-12">
          <span className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-transparent animate-spin" />
          Loading templates…
        </div>
      ) : activeTemplates.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center shadow-sm">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
            <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 00-3.7-3.7 48.678 48.678 0 00-7.324 0 4.006 4.006 0 00-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3l-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 003.7 3.7 48.656 48.656 0 007.324 0 4.006 4.006 0 003.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3l-3 3" />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-900">No engagement templates</p>
          <p className="mt-1 text-sm text-gray-500">
            Create engagement templates in Settings to automate recurring tasks.
          </p>
          <Link
            href="/dashboard/settings/engagements"
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            Create Template
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {activeTemplates.map((template) => (
            <div
              key={template.id}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <h3 className="text-sm font-semibold text-gray-900">{template.name}</h3>
                {template.is_system && (
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600">
                    System
                  </span>
                )}
              </div>
              {template.description && (
                <p className="mt-1 text-xs text-gray-500 line-clamp-2">{template.description}</p>
              )}
              <div className="mt-3 flex items-center gap-3 text-xs text-gray-400">
                <span>{template.tasks.length} task{template.tasks.length !== 1 ? "s" : ""}</span>
                {template.entity_types && template.entity_types.length > 0 && (
                  <span className="capitalize">
                    {template.entity_types.join(", ").replace(/_/g, " ")}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
