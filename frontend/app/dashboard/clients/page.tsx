"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Client, ClientListResponse, createClientsApi } from "@/lib/api";

export default function ClientsPage() {
  const { getToken } = useAuth();
  const [response, setResponse] = useState<ClientListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    createClientsApi(getToken)
      .list()
      .then(setResponse)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [getToken]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <nav className="flex items-center gap-2 text-sm">
            <Link
              href="/dashboard"
              className="font-semibold text-gray-900 hover:text-gray-600 transition-colors"
            >
              AdvisoryBoard
            </Link>
            <span className="text-gray-300">/</span>
            <span className="font-medium text-gray-500">Clients</span>
          </nav>

          <Link
            href="/dashboard/clients/new"
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            + New Client
          </Link>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-gray-900">Clients</h1>
          {response && !loading && (
            <p className="mt-1 text-sm text-gray-500">
              {response.total} {response.total === 1 ? "client" : "clients"}
            </p>
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex justify-center py-20">
            <div className="h-6 w-6 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && response?.items.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white py-20 text-center">
            <p className="text-sm font-medium text-gray-500">No clients yet</p>
            <p className="mt-1 text-xs text-gray-400">
              Add your first client to get started
            </p>
            <Link
              href="/dashboard/clients/new"
              className="mt-5 inline-flex items-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              + New Client
            </Link>
          </div>
        )}

        {/* Table */}
        {!loading && !error && response && response.items.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {["Name", "Business", "Email", "Industry", ""].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {response.items.map((client: Client) => (
                  <tr
                    key={client.id}
                    className="group hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <span className="text-sm font-medium text-gray-900">
                        {client.name}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {client.business_name ?? "—"}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {client.email ?? "—"}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {client.industry ?? "—"}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        href={`/dashboard/clients/${client.id}`}
                        className="text-sm font-medium text-blue-600 hover:text-blue-800 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
