"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ChatSessionSummary,
  createSessionsApi,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  clientId: string;
  activeSessionId: string | null;
  onSessionSelect: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession?: (sessionId: string) => void;
  refreshTrigger?: number;
}

interface DateGroup {
  label: string;
  sessions: ChatSessionSummary[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function groupSessionsByDate(sessions: ChatSessionSummary[]): DateGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);
  const monthAgo = new Date(today.getTime() - 30 * 86400000);

  const groups: Record<string, ChatSessionSummary[]> = {
    Today: [],
    Yesterday: [],
    "This Week": [],
    "This Month": [],
    Earlier: [],
  };

  for (const s of sessions) {
    const d = new Date(s.started_at);
    if (d >= today) groups["Today"].push(s);
    else if (d >= yesterday) groups["Yesterday"].push(s);
    else if (d >= weekAgo) groups["This Week"].push(s);
    else if (d >= monthAgo) groups["This Month"].push(s);
    else groups["Earlier"].push(s);
  }

  return Object.entries(groups)
    .filter(([, list]) => list.length > 0)
    .map(([label, list]) => ({ label, sessions: list }));
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatSidebar({
  clientId,
  activeSessionId,
  onSessionSelect,
  onNewChat,
  onDeleteSession,
  refreshTrigger = 0,
}: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredSessions, setFilteredSessions] = useState<ChatSessionSummary[]>([]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const searchTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // ── Fetch sessions ──────────────────────────────────────────────────────────

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const api = createSessionsApi(getToken, activeOrg?.id);
      // Fetch up to 100 sessions for sidebar display
      const res = await api.getClientSessions(clientId, 1, 100);
      setSessions(res.sessions);
      setFilteredSessions(res.sessions);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, getToken, activeOrg?.id, refreshTrigger]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // ── Client-side search/filter (debounced 300ms) ─────────────────────────────

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);

    if (!searchQuery.trim()) {
      setFilteredSessions(sessions);
      return;
    }

    searchTimer.current = setTimeout(() => {
      const q = searchQuery.toLowerCase();
      setFilteredSessions(
        sessions.filter(
          (s) =>
            (s.title && s.title.toLowerCase().includes(q)) ||
            (s.summary && s.summary.toLowerCase().includes(q)) ||
            (s.key_topics && s.key_topics.some((t) => t.toLowerCase().includes(q)))
        )
      );
    }, 300);

    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchQuery, sessions]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  function handleSessionClick(sessionId: string) {
    onSessionSelect(sessionId);
    setMobileOpen(false);
  }

  function handleNewChat() {
    onNewChat();
    setMobileOpen(false);
  }

  async function handleDeleteSession(sessionId: string) {
    // Optimistic removal
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    setFilteredSessions((prev) => prev.filter((s) => s.id !== sessionId));
    setConfirmDelete(null);
    onDeleteSession?.(sessionId);

    try {
      const api = createSessionsApi(getToken, activeOrg?.id);
      await api.deleteSession(clientId, sessionId);
    } catch {
      // Reload to restore state on error
      loadSessions();
    }
  }

  // ── Sidebar content ─────────────────────────────────────────────────────────

  const groups = groupSessionsByDate(filteredSessions);

  const sidebarContent = (
    <div className="flex h-full flex-col bg-white">
      {/* Header: New Chat + Search */}
      <div className="flex-shrink-0 border-b border-gray-100 p-3">
        <button
          onClick={handleNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          <PlusIcon />
          New Chat
        </button>
        <div className="relative mt-2.5">
          <SearchIcon className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full rounded-lg border border-gray-200 bg-gray-50 py-1.5 pl-8 pr-3 text-xs text-gray-700 placeholder-gray-400 outline-none transition focus:border-blue-400 focus:bg-white focus:ring-1 focus:ring-blue-400"
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-1 p-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="animate-pulse rounded-lg bg-gray-100 p-3">
                <div className="mb-1.5 h-3 w-3/4 rounded bg-gray-200" />
                <div className="h-2.5 w-1/2 rounded bg-gray-200" />
              </div>
            ))}
          </div>
        ) : groups.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
            <MessageSquareIcon className="mb-2 h-8 w-8 text-gray-300" />
            <p className="text-xs text-gray-400">
              {searchQuery
                ? "No conversations match your search."
                : "No conversations yet. Start one by typing below."}
            </p>
          </div>
        ) : (
          <div className="py-1">
            {groups.map((group) => (
              <div key={group.label}>
                <div className="px-3 pb-1 pt-3 text-[10px] font-medium uppercase tracking-wider text-gray-400">
                  {group.label}
                </div>
                {group.sessions.map((s) => {
                  const isActive = s.id === activeSessionId;
                  return (
                    <div
                      key={s.id}
                      className={[
                        "group relative flex w-full items-start px-3 py-2 transition-colors",
                        isActive
                          ? "border-l-2 border-blue-600 bg-blue-50"
                          : "border-l-2 border-transparent hover:bg-gray-50",
                      ].join(" ")}
                    >
                      <button
                        onClick={() => handleSessionClick(s.id)}
                        className="flex min-w-0 flex-1 flex-col text-left"
                      >
                        <div className="flex items-center gap-1.5">
                          {s.ended_at === null && (
                            <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                          )}
                          <span className="truncate text-sm font-medium text-gray-800">
                            {s.title || "Untitled conversation"}
                          </span>
                        </div>
                        {s.summary && (
                          <span className="mt-0.5 truncate text-xs text-gray-500">
                            {s.summary}
                          </span>
                        )}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmDelete(s.id); }}
                        className="ml-1 mt-0.5 flex-shrink-0 rounded p-1 text-gray-300 opacity-0 transition-opacity hover:bg-gray-200 hover:text-red-500 group-hover:opacity-100"
                        aria-label="Delete conversation"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed bottom-20 left-3 z-40 flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg transition-colors hover:bg-blue-700 md:hidden"
        aria-label="Open chat sidebar"
      >
        <SidebarIcon />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/40 md:hidden"
          onClick={() => setMobileOpen(false)}
        >
          <div
            className="h-full w-[300px] shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div className="hidden w-[300px] flex-shrink-0 border-r border-gray-200 md:block">
        {sidebarContent}
      </div>

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-xs rounded-xl bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-gray-900">Delete this conversation?</h3>
            <p className="mt-1.5 text-xs text-gray-500">This cannot be undone.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteSession(confirmDelete)}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Expose reload helper ────────────────────────────────────────────────────

export type ChatSidebarHandle = { reload: () => void };

// ─── Icons ───────────────────────────────────────────────────────────────────

function PlusIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}

function SearchIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
    </svg>
  );
}

function MessageSquareIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
    </svg>
  );
}

function SidebarIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
    </svg>
  );
}
