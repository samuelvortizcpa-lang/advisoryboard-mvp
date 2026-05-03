"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { DeliverableKey } from "@/lib/api";
import { createCadenceApi, DELIVERABLE_KEYS, DELIVERABLE_LABELS } from "@/lib/api";

interface CreateTemplateDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (newTemplateId: string) => void;
}

export default function CreateTemplateDialog({
  open,
  onClose,
  onCreated,
}: CreateTemplateDialogProps) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [flags, setFlags] = useState<Record<DeliverableKey, boolean>>(() =>
    Object.fromEntries(DELIVERABLE_KEYS.map((k) => [k, false])) as Record<DeliverableKey, boolean>,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const api = useCallback(
    () => createCadenceApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  function resetForm() {
    setName("");
    setDescription("");
    setFlags(
      Object.fromEntries(DELIVERABLE_KEYS.map((k) => [k, false])) as Record<DeliverableKey, boolean>,
    );
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api().createTemplate({
        name: name.trim(),
        description: description.trim() || null,
        deliverable_flags: flags,
      });
      resetForm();
      onCreated(result.id);
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create template",
      );
    } finally {
      setSaving(false);
    }
  }

  function handleClose() {
    if (saving) return;
    resetForm();
    onClose();
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-base font-semibold text-gray-900">
          Create Custom Template
        </h2>
        <p className="mt-1 text-xs text-gray-500">
          Choose which deliverables fire for clients assigned to this template.
        </p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              placeholder="e.g. Quarterly Focus"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Optional description"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">
              Deliverables
            </label>
            <div className="space-y-2">
              {DELIVERABLE_KEYS.map((key) => (
                <label
                  key={key}
                  className="flex items-center gap-2 text-sm text-gray-700"
                >
                  <input
                    type="checkbox"
                    checked={flags[key]}
                    onChange={(e) =>
                      setFlags((prev) => ({ ...prev, [key]: e.target.checked }))
                    }
                    className="rounded text-blue-600"
                  />
                  {DELIVERABLE_LABELS[key]}
                </label>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-600">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              disabled={saving}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Creating…
                </>
              ) : (
                "Create"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
