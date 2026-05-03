"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { CadenceTemplateSummary } from "@/lib/api";
import { createCadenceApi } from "@/lib/api";
import CreateTemplateDialog from "@/components/cadence/CreateTemplateDialog";
import FirmDefaultCard from "@/components/cadence/FirmDefaultCard";
import TemplateListSection from "@/components/cadence/TemplateListSection";

export default function CadenceTemplatesPage() {
  const { getToken } = useAuth();
  const { activeOrg, isAdmin: isOrgAdmin } = useOrg();
  const isFirmAdmin = activeOrg !== null && isOrgAdmin;

  const [templates, setTemplates] = useState<CadenceTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const api = useCallback(
    () => createCadenceApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api().listTemplates();
      setTemplates(res.templates);
    } catch {
      setError("Failed to load templates. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  // Non-admin: empty state
  if (!isFirmAdmin) {
    return (
      <div className="px-8 py-8">
        <div className="flex flex-col items-center justify-center rounded-xl border border-gray-200 bg-white py-16 text-center">
          <p className="text-sm text-gray-500">
            Cadence template management is available to firm administrators.
          </p>
          <Link
            href="/dashboard"
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const systemTemplates = templates.filter((t) => t.is_system);
  const customTemplates = templates.filter((t) => !t.is_system);

  return (
    <div className="px-8 py-8 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
            Settings
          </p>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">
            Cadence Templates
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage templates that determine which deliverables fire for your
            clients.
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          + New custom template
        </button>
      </div>

      <FirmDefaultCard isAdmin={isFirmAdmin} />

      {loading ? (
        <div className="space-y-3">
          <div className="h-12 animate-pulse rounded-xl bg-gray-100" />
          <div className="h-12 animate-pulse rounded-xl bg-gray-100" />
          <div className="h-12 animate-pulse rounded-xl bg-gray-100" />
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={fetchTemplates}
            className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <TemplateListSection
            title="System templates"
            templates={systemTemplates}
            basePath="/dashboard/settings/cadence-templates"
          />
          <TemplateListSection
            title="Your custom templates"
            templates={customTemplates}
            basePath="/dashboard/settings/cadence-templates"
            emptyMessage="No custom templates yet. The system templates above cover most firms; create a custom one if you need a specific mix."
          />
        </div>
      )}

      <CreateTemplateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => fetchTemplates()}
      />
    </div>
  );
}
