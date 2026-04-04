"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

interface RecentClient {
  id: string;
  name: string;
  document_count: number;
  action_item_count: number;
  last_activity: string;
}

interface Props {
  clients: RecentClient[];
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export default function ClientCommandCard({ clients }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query.trim()) return clients.slice(0, 5);
    const q = query.toLowerCase();
    return clients.filter((c) => c.name.toLowerCase().includes(q)).slice(0, 5);
  }, [clients, query]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && filtered.length > 0) {
      router.push(`/dashboard/clients/${filtered[0].id}`);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">Your clients</h3>
        <Link href="/dashboard/clients" className="text-xs text-gray-500 hover:text-gray-700">
          View all &rarr;
        </Link>
      </div>

      {/* Search */}
      <div className="relative mt-3">
        <svg
          className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search clients by name..."
          className="h-10 w-full rounded-lg border border-gray-200 bg-gray-50 pl-9 pr-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-300"
        />
      </div>

      {/* Client list */}
      <div className="mt-3">
        {clients.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <p className="text-sm text-gray-500">No clients yet</p>
            <Link
              href="/dashboard/clients/new"
              className="mt-2 rounded-lg bg-[#c9944a] px-4 py-2 text-sm font-medium text-white hover:bg-[#b8843e]"
            >
              + Add your first client
            </Link>
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-400">No clients match &ldquo;{query}&rdquo;</p>
        ) : (
          filtered.map((c) => (
            <Link
              key={c.id}
              href={`/dashboard/clients/${c.id}`}
              className="-mx-2 flex items-center gap-3 rounded-lg border-b border-gray-100 px-2 py-2.5 transition-colors last:border-b-0 hover:bg-gray-50"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50 text-xs font-medium text-blue-700">
                {initials(c.name)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-gray-900">{c.name}</p>
                <p className="text-xs text-gray-500">
                  {c.document_count} doc{c.document_count !== 1 ? "s" : ""}
                  {" \u00B7 "}
                  {c.action_item_count} action item{c.action_item_count !== 1 ? "s" : ""}
                </p>
              </div>
              <span className="shrink-0 text-xs text-gray-400">
                {relativeTime(c.last_activity)}
              </span>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
