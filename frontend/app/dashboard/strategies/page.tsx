"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import type { Client, ClientListResponse } from "@/lib/api";
import { createClientsApi } from "@/lib/api";

export default function StrategiesPage() {
  const { getToken } = useAuth();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    createClientsApi(getToken)
      .list()
      .then((data: ClientListResponse) => {
        if (!cancelled) setClients(data.items);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [getToken]);

  return (
    <div className="px-8 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Advisory
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">Tax Strategies</h1>
        <p className="mt-1 text-sm text-gray-500">
          View and manage tax strategy recommendations for each client.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-12">
          <span className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-transparent animate-spin" />
          Loading clients…
        </div>
      ) : clients.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center shadow-sm">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
            <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-900">No clients yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Add a client to start reviewing tax strategies.
          </p>
          <Link
            href="/dashboard/clients/new"
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            + New Client
          </Link>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60">
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Client Name
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Entity Type
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Strategies
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {clients.map((client) => (
                <tr key={client.id} className="group hover:bg-gray-50/50 transition-colors">
                  <td className="px-4 py-3.5">
                    <Link
                      href={`/dashboard/clients/${client.id}?tab=tax-strategies`}
                      className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                    >
                      {client.name}
                    </Link>
                    {client.business_name && (
                      <p className="text-xs text-gray-400 mt-0.5">{client.business_name}</p>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-sm text-gray-600 capitalize">
                    {client.entity_type?.replace(/_/g, " ") || "—"}
                  </td>
                  <td className="px-4 py-3.5 text-sm text-gray-400">—</td>
                  <td className="px-4 py-3.5 text-right">
                    <Link
                      href={`/dashboard/clients/${client.id}?tab=tax-strategies`}
                      className="text-sm font-medium text-blue-600 hover:text-blue-700 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      View Strategies →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-400">
        Tax strategies are reviewed per client. Select a client above to view their strategy matrix.
      </p>
    </div>
  );
}
