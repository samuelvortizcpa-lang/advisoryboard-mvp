"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { JournalEntry, JournalFeedResponse, createJournalApi } from "@/lib/api";
import AddJournalEntry from "./AddJournalEntry";

// ─── Icons (inline SVGs matching existing codebase pattern) ──────────────────

function PencilIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
    </svg>
  );
}

function TrendingUpIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
    </svg>
  );
}

function TargetIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  );
}

function FileTextIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function PinIcon({ filled }: { filled?: boolean }) {
  return (
    <svg className="h-3.5 w-3.5" fill={filled ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 3.75V16.5L12 14.25 7.5 16.5V3.75m9 0H18A2.25 2.25 0 0120.25 6v12A2.25 2.25 0 0118 20.25H6A2.25 2.25 0 013.75 18V6A2.25 2.25 0 016 3.75h1.5m9 0h-9" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

// ─── Type → icon mapping ─────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, () => React.ReactElement> = {
  manual: PencilIcon,
  financial_change: TrendingUpIcon,
  life_event: HeartIcon,
  strategy_change: TargetIcon,
  communication: MailIcon,
  document_insight: FileTextIcon,
  system: GearIcon,
};

const TYPE_COLORS: Record<string, string> = {
  manual: "bg-gray-100 text-gray-600",
  financial_change: "bg-emerald-50 text-emerald-600",
  life_event: "bg-pink-50 text-pink-600",
  strategy_change: "bg-violet-50 text-violet-600",
  communication: "bg-sky-50 text-sky-600",
  document_insight: "bg-blue-50 text-blue-600",
  system: "bg-gray-50 text-gray-500",
};

const CATEGORY_COLORS: Record<string, string> = {
  income: "bg-green-100 text-green-700",
  deductions: "bg-blue-100 text-blue-700",
  family: "bg-pink-100 text-pink-700",
  property: "bg-orange-100 text-orange-700",
  employment: "bg-purple-100 text-purple-700",
  business: "bg-teal-100 text-teal-700",
  investment: "bg-indigo-100 text-indigo-700",
  compliance: "bg-red-100 text-red-700",
  general: "bg-gray-100 text-gray-600",
};

type FilterChip = "all" | "manual" | "financial_change" | "strategy_change" | "communication" | "document_insight";

const FILTER_CHIPS: { id: FilterChip; label: string }[] = [
  { id: "all", label: "All" },
  { id: "manual", label: "Manual" },
  { id: "financial_change", label: "Financial" },
  { id: "strategy_change", label: "Strategy" },
  { id: "communication", label: "Communications" },
  { id: "document_insight", label: "Documents" },
];

// ─── Component ───────────────────────────────────────────────────────────────

interface Props {
  clientId: string;
  refreshKey?: number;
}

export default function JournalFeed({ clientId, refreshKey = 0 }: Props) {
  const { getToken } = useAuth();

  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterChip>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [showAddModal, setShowAddModal] = useState(false);
  const [togglingPin, setTogglingPin] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const api = createJournalApi(getToken);
  const perPage = 20;

  async function fetchEntries() {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {
        page: String(page),
        per_page: String(perPage),
      };
      if (filter !== "all") params.entry_type = filter;
      if (search.trim()) params.search = search.trim();

      const res = await api.list(clientId, params);
      setEntries(res.entries);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load journal");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchEntries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, filter, page, refreshKey]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchEntries();
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleTogglePin(entryId: string) {
    setTogglingPin(entryId);
    try {
      await api.togglePin(entryId);
      fetchEntries();
    } catch {
      // silent
    } finally {
      setTogglingPin(null);
    }
  }

  async function handleDelete(entryId: string) {
    if (!confirm("Delete this journal entry?")) return;
    setDeletingId(entryId);
    try {
      await api.delete(entryId);
      fetchEntries();
    } catch {
      // silent
    } finally {
      setDeletingId(null);
    }
  }

  const pinnedEntries = entries.filter((e) => e.is_pinned);
  const unpinnedEntries = entries.filter((e) => !e.is_pinned);
  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Client Journal</h2>
          <p className="mt-0.5 text-sm text-gray-500">
            {total} {total === 1 ? "entry" : "entries"}
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white shadow-sm hover:bg-blue-700"
        >
          <PlusIcon />
          Add Entry
        </button>
      </div>

      {/* Search + Filters */}
      <div className="space-y-3">
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <SearchIcon />
          </div>
          <input
            type="text"
            placeholder="Search journal entries..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="block w-full rounded-lg border border-gray-200 bg-white py-2 pl-10 pr-3 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {FILTER_CHIPS.map((chip) => (
            <button
              key={chip.id}
              onClick={() => { setFilter(chip.id); setPage(1); }}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                filter === chip.id
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-10">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      )}

      {/* Empty */}
      {!loading && entries.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center">
          <p className="text-sm text-gray-500">
            {search ? "No entries match your search" : "No journal entries yet"}
          </p>
          {!search && (
            <button
              onClick={() => setShowAddModal(true)}
              className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Add the first entry
            </button>
          )}
        </div>
      )}

      {/* Feed */}
      {!loading && entries.length > 0 && (
        <div className="space-y-3">
          {/* Pinned section */}
          {pinnedEntries.length > 0 && (
            <>
              <div className="flex items-center gap-2 text-xs font-medium text-amber-600">
                <PinIcon filled />
                <span>Pinned</span>
              </div>
              {pinnedEntries.map((entry) => (
                <EntryCard
                  key={entry.id}
                  entry={entry}
                  expanded={expandedIds.has(entry.id)}
                  onToggleExpand={() => toggleExpand(entry.id)}
                  onTogglePin={() => handleTogglePin(entry.id)}
                  onDelete={() => handleDelete(entry.id)}
                  pinLoading={togglingPin === entry.id}
                  deleteLoading={deletingId === entry.id}
                />
              ))}
              {unpinnedEntries.length > 0 && (
                <div className="border-t border-gray-100" />
              )}
            </>
          )}

          {/* Regular entries */}
          {unpinnedEntries.map((entry) => (
            <EntryCard
              key={entry.id}
              entry={entry}
              expanded={expandedIds.has(entry.id)}
              onToggleExpand={() => toggleExpand(entry.id)}
              onTogglePin={() => handleTogglePin(entry.id)}
              onDelete={() => handleDelete(entry.id)}
              pinLoading={togglingPin === entry.id}
              deleteLoading={deletingId === entry.id}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}

      {/* Add Entry Modal */}
      {showAddModal && (
        <AddJournalEntry
          clientId={clientId}
          onClose={() => setShowAddModal(false)}
          onCreated={() => {
            setShowAddModal(false);
            setPage(1);
            fetchEntries();
          }}
        />
      )}
    </div>
  );
}

// ─── Entry Card ──────────────────────────────────────────────────────────────

function EntryCard({
  entry,
  expanded,
  onToggleExpand,
  onTogglePin,
  onDelete,
  pinLoading,
  deleteLoading,
}: {
  entry: JournalEntry;
  expanded: boolean;
  onToggleExpand: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
  pinLoading: boolean;
  deleteLoading: boolean;
}) {
  const Icon = TYPE_ICONS[entry.entry_type] ?? GearIcon;
  const typeColor = TYPE_COLORS[entry.entry_type] ?? TYPE_COLORS.system;
  const catColor = entry.category ? CATEGORY_COLORS[entry.category] ?? CATEGORY_COLORS.general : null;

  const dateStr = entry.effective_date
    ? new Date(entry.effective_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : new Date(entry.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  const content = entry.content || "";
  const isLong = content.length > 200;
  const displayContent = expanded ? content : content.slice(0, 200);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${typeColor}`}>
          <Icon />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-gray-900">{entry.title}</h3>
                {entry.is_pinned && (
                  <span className="text-amber-500">
                    <PinIcon filled />
                  </span>
                )}
                {catColor && (
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${catColor}`}>
                    {entry.category}
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-gray-400">
                <span>{dateStr}</span>
                <span className="capitalize">{entry.entry_type.replace(/_/g, " ")}</span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={onTogglePin}
                disabled={pinLoading}
                title={entry.is_pinned ? "Unpin" : "Pin"}
                className={`rounded p-1 transition-colors ${
                  entry.is_pinned
                    ? "text-amber-500 hover:bg-amber-50"
                    : "text-gray-300 hover:bg-gray-100 hover:text-gray-500"
                } disabled:opacity-50`}
              >
                <PinIcon filled={entry.is_pinned} />
              </button>
              {entry.entry_type === "manual" && (
                <button
                  onClick={onDelete}
                  disabled={deleteLoading}
                  title="Delete"
                  className="rounded p-1 text-gray-300 transition-colors hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
                >
                  <TrashIcon />
                </button>
              )}
            </div>
          </div>

          {/* Body */}
          {content && (
            <div className="mt-2">
              <p className="whitespace-pre-wrap text-sm text-gray-600">{displayContent}{isLong && !expanded && "..."}</p>
              {isLong && (
                <button
                  onClick={onToggleExpand}
                  className="mt-1 text-xs font-medium text-blue-600 hover:text-blue-700"
                >
                  {expanded ? "Show less" : "Show more"}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
