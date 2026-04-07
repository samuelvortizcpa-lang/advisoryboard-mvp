"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import {
  EngagementTemplate,
  CreateTemplateData,
  createEngagementsApi,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";

const MONTH_NAMES = [
  "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const RECURRENCE_LABELS: Record<string, string> = {
  annual: "Annual",
  quarterly: "Quarterly",
  monthly: "Monthly",
  one_time: "One-time",
};

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-gray-100 text-gray-600",
};

export default function EngagementsSettingsPage() {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [templates, setTemplates] = useState<EngagementTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Create template modal
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateTemplateData>({
    name: "",
    description: "",
    entity_types: [],
  });
  const [creating, setCreating] = useState(false);

  const loadTemplates = useCallback(async () => {
    try {
      const api = createEngagementsApi(getToken, activeOrg?.id);
      const data = await api.listTemplates();
      setTemplates(data);
    } catch {
      /* non-fatal */
    } finally {
      setLoading(false);
    }
  }, [getToken, activeOrg?.id]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  async function handleCreate() {
    if (!createForm.name.trim()) return;
    setCreating(true);
    try {
      const api = createEngagementsApi(getToken, activeOrg?.id);
      const newTemplate = await api.createTemplate({
        name: createForm.name.trim(),
        description: createForm.description?.trim() || undefined,
        entity_types: createForm.entity_types?.length ? createForm.entity_types : undefined,
      });
      setTemplates((prev) => [...prev, newTemplate]);
      setShowCreate(false);
      setCreateForm({ name: "", description: "", entity_types: [] });
    } catch {
      /* non-fatal */
    } finally {
      setCreating(false);
    }
  }

  // Separate system and custom templates
  const systemTemplates = templates.filter((t) => t.is_system);
  const customTemplates = templates.filter((t) => !t.is_system);

  return (
    <div className="px-8 py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Engagement Templates</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage recurring compliance workflows. System templates cover standard tax deadlines.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Create Template
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        </div>
      )}

      {!loading && (
        <div className="space-y-6">
          {/* System templates */}
          {systemTemplates.length > 0 && (
            <div>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
                System Templates
              </h2>
              <div className="space-y-2">
                {systemTemplates.map((t) => (
                  <TemplateCard
                    key={t.id}
                    template={t}
                    expanded={expandedId === t.id}
                    onToggle={() => setExpandedId(expandedId === t.id ? null : t.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Custom templates */}
          <div>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Custom Templates
            </h2>
            {customTemplates.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-200 px-6 py-10 text-center">
                <p className="text-sm text-gray-400">
                  No custom templates yet. Create one to define your own recurring workflows.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {customTemplates.map((t) => (
                  <TemplateCard
                    key={t.id}
                    template={t}
                    expanded={expandedId === t.id}
                    onToggle={() => setExpandedId(expandedId === t.id ? null : t.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create template modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Create Template</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g., Quarterly Payroll Filing"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={createForm.description ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                  rows={2}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setShowCreate(false)}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !createForm.name.trim()}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Template card ──────────────────────────────────────────────────────────

function TemplateCard({
  template,
  expanded,
  onToggle,
}: {
  template: EngagementTemplate;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-gray-50"
      >
        <div className="flex items-center gap-3 min-w-0">
          {template.is_system ? (
            <span className="shrink-0 text-gray-300" title="System template">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
              </svg>
            </span>
          ) : (
            <span className="shrink-0 text-indigo-400">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </span>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{template.name}</p>
            {template.description && (
              <p className="text-xs text-gray-400 truncate">{template.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
            {template.tasks.length} task{template.tasks.length !== 1 ? "s" : ""}
          </span>
          {template.entity_types && template.entity_types.length > 0 && (
            <span className="text-xs text-gray-400">
              {template.entity_types.join(", ")}
            </span>
          )}
          <svg
            className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </div>
      </button>

      {expanded && template.tasks.length > 0 && (
        <div className="border-t border-gray-100">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-50 bg-gray-50/50">
                <th className="py-2 pl-4 pr-2 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400">Task</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400">Date</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400">Recurrence</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400">Lead</th>
                <th className="px-2 py-2 pr-4 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400">Priority</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {template.tasks.map((task) => (
                <tr key={task.id} className="hover:bg-gray-50/50">
                  <td className="py-2 pl-4 pr-2 text-gray-700">{task.task_name}</td>
                  <td className="px-2 py-2 text-gray-500">
                    {task.month && task.day
                      ? `${MONTH_NAMES[task.month]} ${task.day}`
                      : "—"}
                  </td>
                  <td className="px-2 py-2 text-gray-500">
                    {RECURRENCE_LABELS[task.recurrence] ?? task.recurrence}
                  </td>
                  <td className="px-2 py-2 text-gray-500">
                    {task.lead_days}d
                  </td>
                  <td className="px-2 py-2 pr-4">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${PRIORITY_COLORS[task.priority] ?? "bg-gray-100 text-gray-500"}`}>
                      {task.priority}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {expanded && template.tasks.length === 0 && (
        <div className="border-t border-gray-100 px-4 py-4 text-center text-sm text-gray-400">
          No tasks defined yet.
        </div>
      )}
    </div>
  );
}
