"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { CadenceTemplateSummary } from "@/lib/api";
import { createCadenceApi } from "@/lib/api";

interface FirmDefaultCardProps {
  isAdmin: boolean;
}

export default function FirmDefaultCard({ isAdmin }: FirmDefaultCardProps) {
  const { getToken } = useAuth();
  const { activeOrg, refreshOrgs } = useOrg();

  const [templates, setTemplates] = useState<CadenceTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const api = useCallback(
    () => createCadenceApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  useEffect(() => {
    let cancelled = false;
    api()
      .listTemplates()
      .then((res) => {
        if (!cancelled) setTemplates(res.templates);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const currentDefaultId = activeOrg?.default_cadence_template_id ?? null;
  const currentTemplate = templates.find((t) => t.id === currentDefaultId);

  async function handleConfirm() {
    if (!activeOrg) return;
    setSaving(true);
    setError(null);
    try {
      await api().setFirmDefault(activeOrg.id, selectedId);
      await refreshOrgs();
      setPicking(false);
      setSelectedId(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update firm default",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="h-20 animate-pulse rounded-xl bg-gray-100" />
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Firm Default Template
          </h3>
          <p className="mt-0.5 text-xs text-gray-500">
            {currentTemplate
              ? `Currently using: ${currentTemplate.name}`
              : "No firm default set"}
          </p>
        </div>
        {isAdmin && !picking && (
          <button
            onClick={() => {
              setPicking(true);
              setSelectedId(currentDefaultId);
            }}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            Change
          </button>
        )}
      </div>

      {picking && (
        <div className="mt-4 space-y-3">
          <div className="space-y-1">
            {templates
              .filter((t) => t.is_active)
              .map((t) => (
                <label
                  key={t.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                    selectedId === t.id
                      ? "bg-blue-50 text-blue-700"
                      : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="firm-default"
                    value={t.id}
                    checked={selectedId === t.id}
                    onChange={() => setSelectedId(t.id)}
                    className="text-blue-600"
                  />
                  <span>{t.name}</span>
                  <span
                    className={`ml-auto text-xs ${
                      t.is_system ? "text-purple-500" : "text-blue-500"
                    }`}
                  >
                    {t.is_system ? "System" : "Custom"}
                  </span>
                </label>
              ))}
            <label
              className={`flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                selectedId === null
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-700 hover:bg-gray-50"
              }`}
            >
              <input
                type="radio"
                name="firm-default"
                checked={selectedId === null}
                onChange={() => setSelectedId(null)}
                className="text-blue-600"
              />
              <span className="italic text-gray-500">Clear default</span>
            </label>
          </div>

          {error && (
            <p className="text-xs text-red-600">{error}</p>
          )}

          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setPicking(false);
                setSelectedId(null);
                setError(null);
              }}
              disabled={saving}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={saving || selectedId === currentDefaultId}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? (
                <>
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Saving…
                </>
              ) : (
                "Confirm"
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
