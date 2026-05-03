"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { useOrg } from "@/contexts/OrgContext";
import type { CadenceTemplateSummary } from "@/lib/api";
import { createCadenceApi } from "@/lib/api";

interface AssignTemplateDrawerProps {
  open: boolean;
  onClose: () => void;
  currentTemplateId: string | null;
  onAssign: (templateId: string) => Promise<void>;
}

export default function AssignTemplateDrawer({
  open,
  onClose,
  currentTemplateId,
  onAssign,
}: AssignTemplateDrawerProps) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const [templates, setTemplates] = useState<CadenceTemplateSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createCadenceApi(getToken, activeOrg?.id);
      const res = await api.listTemplates();
      setTemplates(res.templates.filter((t) => t.is_active));
    } catch {
      setError("Failed to load templates. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [getToken, activeOrg?.id]);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    setError(null);
    fetchTemplates();
  }, [open, fetchTemplates]);

  async function handleConfirm() {
    if (!selected) return;
    setConfirming(true);
    try {
      await onAssign(selected);
      onClose();
    } catch {
      setError("Failed to assign template. Please try again.");
    } finally {
      setConfirming(false);
    }
  }

  if (!open) return null;

  const systemTemplates = templates.filter((t) => t.is_system);
  const customTemplates = templates.filter((t) => !t.is_system);
  const canConfirm = selected !== null && selected !== currentTemplateId && !confirming;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />

      {/* Drawer panel */}
      <div className="relative w-full max-w-md bg-white shadow-xl">
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="border-b border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">
                Assign cadence template
              </h2>
              <button
                onClick={onClose}
                className="rounded-md p-1 text-gray-400 hover:text-gray-500"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {loading && (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 animate-pulse rounded-lg bg-gray-100" />
                ))}
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                <p>{error}</p>
                <button
                  onClick={fetchTemplates}
                  className="mt-2 text-xs font-medium text-red-600 underline hover:text-red-700"
                >
                  Retry
                </button>
              </div>
            )}

            {!loading && !error && (
              <>
                {systemTemplates.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                      System templates
                    </p>
                    <div className="space-y-2">
                      {systemTemplates.map((t) => (
                        <TemplateRow
                          key={t.id}
                          template={t}
                          isCurrent={t.id === currentTemplateId}
                          isSelected={t.id === selected}
                          onSelect={() => setSelected(t.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {customTemplates.length > 0 && (
                  <div className={systemTemplates.length > 0 ? "mt-6" : ""}>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                      Your custom templates
                    </p>
                    <div className="space-y-2">
                      {customTemplates.map((t) => (
                        <TemplateRow
                          key={t.id}
                          template={t}
                          isCurrent={t.id === currentTemplateId}
                          isSelected={t.id === selected}
                          onSelect={() => setSelected(t.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {templates.length === 0 && (
                  <p className="text-center text-sm text-gray-500">
                    No active templates available.
                  </p>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-gray-200 px-6 py-4">
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                disabled={!canConfirm}
                className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {confirming ? "Assigning..." : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TemplateRow({
  template,
  isCurrent,
  isSelected,
  onSelect,
}: {
  template: CadenceTemplateSummary;
  isCurrent: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={[
        "w-full rounded-lg border p-3 text-left transition-colors",
        isSelected
          ? "border-blue-500 bg-blue-50"
          : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-900">{template.name}</p>
          {template.description && (
            <p className="mt-0.5 text-xs text-gray-500">{template.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isCurrent && (
            <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-medium text-green-700">
              Current
            </span>
          )}
          <div
            className={[
              "h-4 w-4 rounded-full border-2",
              isSelected
                ? "border-blue-600 bg-blue-600"
                : "border-gray-300 bg-white",
            ].join(" ")}
          />
        </div>
      </div>
    </button>
  );
}
