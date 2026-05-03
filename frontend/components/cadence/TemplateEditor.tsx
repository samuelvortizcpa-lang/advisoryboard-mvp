"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { CadenceTemplateDetailResponse, DeliverableKey } from "@/lib/api";
import { createCadenceApi, DELIVERABLE_KEYS, DELIVERABLE_LABELS } from "@/lib/api";

interface TemplateEditorProps {
  template: CadenceTemplateDetailResponse;
  isAdmin: boolean;
  onSaved: (updated: CadenceTemplateDetailResponse) => void;
  onDeactivated: () => void;
}

export default function TemplateEditor({
  template,
  isAdmin,
  onSaved,
  onDeactivated,
}: TemplateEditorProps) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [name, setName] = useState(template.name);
  const [description, setDescription] = useState(template.description ?? "");
  const [flags, setFlags] = useState<Record<DeliverableKey, boolean>>(
    template.deliverable_flags,
  );
  const [saving, setSaving] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  // Reset local state when template prop changes
  useEffect(() => {
    setName(template.name);
    setDescription(template.description ?? "");
    setFlags(template.deliverable_flags);
    setError(null);
    setDeactivateError(null);
  }, [template]);

  const api = useCallback(
    () => createCadenceApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  const hasChanges =
    name !== template.name ||
    description !== (template.description ?? "") ||
    DELIVERABLE_KEYS.some((k) => flags[k] !== template.deliverable_flags[k]);

  function handleCancel() {
    setName(template.name);
    setDescription(template.description ?? "");
    setFlags(template.deliverable_flags);
    setError(null);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api().updateTemplate(template.id, {
        name: name.trim(),
        description: description.trim() || null,
        deliverable_flags: flags,
      });
      onSaved(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save changes",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate() {
    setDeactivating(true);
    setDeactivateError(null);
    try {
      await api().deactivateTemplate(template.id);
      onDeactivated();
    } catch (err) {
      setDeactivateError(
        err instanceof Error
          ? err.message
          : "Failed to deactivate template",
      );
    } finally {
      setDeactivating(false);
    }
  }

  const isEditable = !template.is_system && isAdmin;

  // System template: read-only
  if (template.is_system) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg border border-purple-100 bg-purple-50 px-4 py-2.5">
          <p className="text-sm font-medium text-purple-700">
            System template (read-only)
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-500">Name</label>
          <p className="mt-1 text-sm text-gray-900">{template.name}</p>
        </div>

        {template.description && (
          <div>
            <label className="block text-sm font-medium text-gray-500">
              Description
            </label>
            <p className="mt-1 text-sm text-gray-900">{template.description}</p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-500">
            Deliverables
          </label>
          <div className="mt-2 space-y-2">
            {DELIVERABLE_KEYS.map((key) => (
              <div key={key} className="flex items-center gap-2 text-sm">
                <span
                  className={`h-2 w-2 rounded-full ${
                    template.deliverable_flags[key]
                      ? "bg-green-500"
                      : "bg-gray-300"
                  }`}
                />
                <span className="text-gray-700">
                  {DELIVERABLE_LABELS[key]}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Custom template: editable if admin
  return (
    <div className="space-y-6">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={!isEditable}
          maxLength={100}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Description
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={!isEditable}
          rows={2}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500"
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
                disabled={!isEditable}
                className="rounded text-blue-600 disabled:opacity-50"
              />
              {DELIVERABLE_LABELS[key]}
            </label>
          ))}
        </div>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {isEditable && (
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges || !name.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Saving…
              </>
            ) : (
              "Save changes"
            )}
          </button>
          <button
            onClick={handleCancel}
            disabled={saving || !hasChanges}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      )}

      {isEditable && (
        <>
          <hr className="border-gray-200" />
          <div>
            <h4 className="text-sm font-semibold text-red-700">Danger zone</h4>
            <p className="mt-1 text-xs text-gray-500">
              Deactivating a template hides it from new assignments. Existing
              client cadences are not affected.
            </p>
            {deactivateError && (
              <p className="mt-2 text-xs text-red-600">{deactivateError}</p>
            )}
            <button
              onClick={handleDeactivate}
              disabled={deactivating}
              className="mt-3 inline-flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50"
            >
              {deactivating ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-red-400 border-t-transparent" />
                  Deactivating…
                </>
              ) : (
                "Deactivate template"
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
