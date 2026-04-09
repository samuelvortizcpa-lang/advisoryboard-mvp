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
}: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredSessions, setFilteredSessions] = useState<ChatSessionSummary[]>([]);
  const [mobileOpen, setMobileOpen] = useState(false);

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
  }, [clientId, getToken, activeOrg?.id]);

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
                    <button
                      key={s.id}
                      onClick={() => handleSessionClick(s.id)}
                      className={[
                        "group flex w-full flex-col px-3 py-2 text-left transition-colors",
                        isActive
                          ? "border-l-2 border-blue-600 bg-blue-50"
                          : "border-l-2 border-transparent hover:bg-gray-50",
                      ].join(" ")}
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
