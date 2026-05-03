"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { CadenceTemplateDetailResponse } from "@/lib/api";
import { createCadenceApi } from "@/lib/api";
import TemplateEditor from "@/components/cadence/TemplateEditor";

export default function CadenceTemplateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { getToken } = useAuth();
  const { activeOrg, isAdmin: isOrgAdmin } = useOrg();
  const isFirmAdmin = activeOrg !== null && isOrgAdmin;

  const [template, setTemplate] = useState<CadenceTemplateDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const api = useCallback(
    () => createCadenceApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  const fetchTemplate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const data = await api().getTemplate(id);
      setTemplate(data);
    } catch (err) {
      if ((err as { status?: number }).status === 404) {
        setNotFound(true);
      } else {
        setError("Failed to load template. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }, [api, id]);

  useEffect(() => {
    fetchTemplate();
  }, [fetchTemplate]);

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

  if (loading) {
    return (
      <div className="px-8 py-8 space-y-4">
        <div className="h-6 w-40 animate-pulse rounded bg-gray-100" />
        <div className="h-64 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="px-8 py-8">
        <div className="flex flex-col items-center justify-center rounded-xl border border-gray-200 bg-white py-16 text-center">
          <p className="text-sm text-gray-500">Template not found.</p>
          <Link
            href="/dashboard/settings/cadence-templates"
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Back to Templates
          </Link>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-8 py-8">
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={fetchTemplate}
            className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-8 space-y-6">
      <div>
        <Link
          href="/dashboard/settings/cadence-templates"
          className="inline-flex items-center gap-1 text-sm text-gray-500 transition-colors hover:text-gray-700"
        >
          <svg
            className="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.75 19.5L8.25 12l7.5-7.5"
            />
          </svg>
          Back to Templates
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">
          {template!.name}
        </h1>
      </div>

      <div className="max-w-lg rounded-xl border border-gray-200 bg-white p-6">
        <TemplateEditor
          template={template!}
          isAdmin={isFirmAdmin}
          onSaved={(updated) => setTemplate(updated)}
          onDeactivated={() => router.push("/dashboard/settings/cadence-templates")}
        />
      </div>
    </div>
  );
}
