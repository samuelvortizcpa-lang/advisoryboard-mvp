"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Client, ClientListResponse, createClientsApi } from "@/lib/api";

// ─── Color map for client-type badges ─────────────────────────────────────────

const TYPE_BADGE: Record<string, string> = {
  blue: "bg-blue-50 text-blue-700",
  green: "bg-green-50 text-green-700",
  purple: "bg-purple-50 text-purple-700",
  red: "bg-red-50 text-red-700",
  gray: "bg-gray-100 text-gray-600",
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ClientsPage() {
  const { getToken } = useAuth();
  const router = useRouter();

  const [response, setResponse] = useState<ClientListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Delete state
  const [deleteTarget, setDeleteTarget] = useState<Client | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    createClientsApi(getToken)
      .list()
      .then(setResponse)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [getToken]);

  // Client-side search filter
  const filteredItems = (response?.items ?? []).filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      (c.business_name?.toLowerCase().includes(q) ?? false) ||
      (c.industry?.toLowerCase().includes(q) ?? false) ||
      (c.client_type?.name.toLowerCase().includes(q) ?? false)
    );
  });

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await createClientsApi(getToken).delete(deleteTarget.id);
      setResponse((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.filter((c) => c.id !== deleteTarget.id),
              total: prev.total - 1,
            }
          : null
      );
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete client");
      setDeleteTarget(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <div className="px-8 py-8">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Clients</h1>
          {!loading && response && (
            <p className="mt-0.5 text-sm text-gray-500">
              {response.total} {response.total === 1 ? "client" : "clients"}
            </p>
          )}
        </div>
        <Link
          href="/dashboard/clients/new"
          className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          + New Client
        </Link>
      </div>

      {/* ── Search ───────────────────────────────────────────────────────── */}
      <div className="relative mb-4 w-64">
        <svg
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <input
          type="text"
          placeholder="Search clients…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-md border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Loading ──────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      )}

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {!loading && !error && filteredItems.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white py-20 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
            <svg
              className="h-6 w-6 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-900">
            {searchQuery.trim() ? "No clients match your search" : "No clients yet"}
          </p>
          <p className="mt-1 text-xs text-gray-400">
            {searchQuery.trim()
              ? "Try a different search term"
              : "Add your first client to get started"}
          </p>
          {!searchQuery.trim() && (
            <Link
              href="/dashboard/clients/new"
              className="mt-5 inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              + New Client
            </Link>
          )}
        </div>
      )}

      {/* ── Table ────────────────────────────────────────────────────────── */}
      {!loading && !error && filteredItems.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60">
                {["Name", "Type", "Industry", "Documents", "Last Activity", ""].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-400"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filteredItems.map((client) => (
                <tr
                  key={client.id}
                  className="group cursor-pointer transition-colors hover:bg-gray-50"
                  onClick={() => router.push(`/dashboard/clients/${client.id}`)}
                >
                  {/* Name */}
                  <td className="px-4 py-3.5">
                    <p className="text-sm font-medium text-gray-900">
                      {client.name}
                    </p>
                    {client.business_name && (
                      <p className="text-xs text-gray-400">
                        {client.business_name}
                      </p>
                    )}
                  </td>

                  {/* Type */}
                  <td className="px-4 py-3.5">
                    {client.client_type ? (
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                          TYPE_BADGE[client.client_type.color] ??
                          "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {client.client_type.name}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>

                  {/* Industry */}
                  <td className="px-4 py-3.5 text-sm text-gray-600">
                    {client.industry ?? (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>

                  {/* Documents — not available from list endpoint */}
                  <td className="px-4 py-3.5 text-sm text-gray-300">—</td>

                  {/* Last Activity */}
                  <td className="px-4 py-3.5 text-sm text-gray-500">
                    {formatRelativeDate(client.updated_at)}
                  </td>

                  {/* Actions (visible on row hover) */}
                  <td className="px-4 py-3.5">
                    <div
                      className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Link
                        href={`/dashboard/clients/${client.id}`}
                        title="View / Edit"
                        className="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
                      >
                        <PencilIcon />
                      </Link>
                      <button
                        title="Delete client"
                        onClick={() => setDeleteTarget(client)}
                        className="rounded p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Delete confirmation modal ─────────────────────────────────────── */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">
              Delete client?
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              This will permanently delete{" "}
              <strong>{deleteTarget.name}</strong> and all associated documents
              and data. This cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleteLoading}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteLoading}
                className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
              >
                {deleteLoading && <SmallSpinner />}
                {deleteLoading ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeDate(iso: string): string {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const diffDays = Math.floor(diffMs / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function PencilIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
      />
    </svg>
  );
}

function SmallSpinner() {
  return (
    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
  );
}
