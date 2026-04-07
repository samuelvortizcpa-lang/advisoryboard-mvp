"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import {
  ChatSessionSummary,
  ChatSessionDetail,
  QAPairResult,
  SessionSearchResult,
  createSessionsApi,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";

interface Props {
  clientId: string;
}

export default function SessionHistory({ clientId }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [expanded, setExpanded] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<{
    sessions: SessionSearchResult[];
    qa_pairs: QAPairResult[];
  } | null>(null);

  // Expanded session transcript
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<ChatSessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  function api() {
    return createSessionsApi(getToken, activeOrg?.id);
  }

  async function loadSessions() {
    setLoading(true);
    try {
      const res = await api().getClientSessions(clientId, 1, 5);
      setSessions(res.sessions);
      setTotal(res.total);
      setLoaded(true);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    } finally {
      setLoading(false);
    }
  }

  // Load sessions when panel is first expanded
  useEffect(() => {
    if (expanded && !loaded) {
      loadSessions();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded]);

  async function handleSearch() {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const res = await api().searchSessions(clientId, q);
      setSearchResults(res);
    } catch (err) {
      console.error("Session search failed:", err);
    } finally {
      setSearching(false);
    }
  }

  async function toggleSessionDetail(sessionId: string) {
    if (expandedSession === sessionId) {
      setExpandedSession(null);
      setSessionDetail(null);
      return;
    }
    setExpandedSession(sessionId);
    setDetailLoading(true);
    try {
      const detail = await api().getSessionDetail(clientId, sessionId);
      setSessionDetail(detail);
    } catch (err) {
      console.error("Failed to load session detail:", err);
    } finally {
      setDetailLoading(false);
    }
  }

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return (
    <div className="border-b border-gray-100">
      {/* Toggle header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-2 text-xs text-gray-500 hover:bg-gray-50 transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <HistoryIcon />
          Past conversations
          {loaded && total > 0 && (
            <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
              {total}
            </span>
          )}
        </span>
        <svg
          className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50/50 px-4 py-3">
          {/* Search bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSearch();
            }}
            className="flex items-center gap-2 mb-3"
          >
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search past conversations..."
              className="flex-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 placeholder-gray-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
            />
            <button
              type="submit"
              disabled={searching || !searchQuery.trim()}
              className="rounded-md bg-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-300 disabled:opacity-40 transition-colors"
            >
              {searching ? "..." : "Search"}
            </button>
            {searchResults && (
              <button
                type="button"
                onClick={() => {
                  setSearchResults(null);
                  setSearchQuery("");
                }}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                Clear
              </button>
            )}
          </form>

          {/* Search results */}
          {searchResults && (
            <div className="mb-3 space-y-2">
              {searchResults.sessions.length === 0 && searchResults.qa_pairs.length === 0 ? (
                <p className="text-xs text-gray-400 text-center py-2">No matching conversations found</p>
              ) : (
                <>
                  {searchResults.qa_pairs.length > 0 && (
                    <div>
                      <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1">
                        Matching Q&A
                      </p>
                      {searchResults.qa_pairs.slice(0, 3).map((qa, i) => (
                        <QAPairCard key={i} qa={qa} />
                      ))}
                    </div>
                  )}
                  {searchResults.sessions.length > 0 && (
                    <div>
                      <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1">
                        Matching sessions
                      </p>
                      {searchResults.sessions.map((s) => (
                        <SessionCard
                          key={s.id}
                          session={s}
                          isExpanded={expandedSession === s.id}
                          onToggle={() => toggleSessionDetail(s.id)}
                          detail={expandedSession === s.id ? sessionDetail : null}
                          detailLoading={expandedSession === s.id && detailLoading}
                          formatDate={formatDate}
                          showScore
                        />
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Recent sessions list */}
          {!searchResults && (
            <>
              {loading ? (
                <div className="flex items-center justify-center py-4 text-xs text-gray-400">
                  <svg className="animate-spin w-4 h-4 mr-1.5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Loading...
                </div>
              ) : sessions.length === 0 ? (
                <p className="text-xs text-gray-400 text-center py-3">
                  No past conversations yet
                </p>
              ) : (
                <div className="space-y-1">
                  {sessions.map((s) => (
                    <SessionCard
                      key={s.id}
                      session={s}
                      isExpanded={expandedSession === s.id}
                      onToggle={() => toggleSessionDetail(s.id)}
                      detail={expandedSession === s.id ? sessionDetail : null}
                      detailLoading={expandedSession === s.id && detailLoading}
                      formatDate={formatDate}
                    />
                  ))}
                  {total > 5 && (
                    <p className="text-[10px] text-gray-400 text-center pt-1">
                      {total - 5} more conversation{total - 5 !== 1 ? "s" : ""} — use search to find them
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SessionCard({
  session,
  isExpanded,
  onToggle,
  detail,
  detailLoading,
  formatDate,
  showScore,
}: {
  session: ChatSessionSummary | SessionSearchResult;
  isExpanded: boolean;
  onToggle: () => void;
  detail: ChatSessionDetail | null;
  detailLoading: boolean;
  formatDate: (d: string) => string;
  showScore?: boolean;
}) {
  const score = showScore && "similarity_score" in session ? session.similarity_score : null;

  return (
    <div className="rounded-md border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-start gap-2 px-2.5 py-2 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-700 truncate">
            {session.title || "Untitled conversation"}
          </p>
          {session.summary && (
            <p className="mt-0.5 text-[11px] text-gray-400 line-clamp-2">
              {session.summary}
            </p>
          )}
          <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-400">
            <span>{formatDate(session.started_at)}</span>
            <span>·</span>
            <span>{session.message_count} msg{session.message_count !== 1 ? "s" : ""}</span>
            {score !== null && (
              <>
                <span>·</span>
                <span className="text-blue-500">{Math.round(score)}% match</span>
              </>
            )}
          </div>
          {session.key_topics && session.key_topics.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {session.key_topics.slice(0, 4).map((topic, i) => (
                <span
                  key={i}
                  className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] text-gray-500"
                >
                  {topic}
                </span>
              ))}
            </div>
          )}
        </div>
        <svg
          className={`h-3.5 w-3.5 flex-shrink-0 text-gray-400 transition-transform mt-0.5 ${
            isExpanded ? "rotate-180" : ""
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Inline transcript */}
      {isExpanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-2.5 py-2 max-h-48 overflow-y-auto">
          {detailLoading ? (
            <p className="text-[10px] text-gray-400 text-center py-2">Loading transcript...</p>
          ) : detail && detail.messages.length > 0 ? (
            <div className="space-y-1.5">
              {detail.messages.map((msg) => (
                <div key={msg.id} className="text-[11px]">
                  <span
                    className={`font-medium ${
                      msg.role === "user" ? "text-blue-600" : "text-gray-600"
                    }`}
                  >
                    {msg.role === "user" ? "You" : "AI"}:
                  </span>{" "}
                  <span className="text-gray-500">
                    {msg.content.length > 200 ? msg.content.slice(0, 200) + "..." : msg.content}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[10px] text-gray-400 text-center py-2">No messages in this session</p>
          )}
        </div>
      )}
    </div>
  );
}

function QAPairCard({ qa }: { qa: QAPairResult }) {
  return (
    <div className="rounded-md border border-blue-100 bg-blue-50/50 px-2.5 py-2 mb-1">
      <p className="text-[11px] font-medium text-gray-700">
        Q: {qa.question.length > 100 ? qa.question.slice(0, 100) + "..." : qa.question}
      </p>
      <p className="mt-0.5 text-[11px] text-gray-500">
        A: {qa.answer.length > 150 ? qa.answer.slice(0, 150) + "..." : qa.answer}
      </p>
      <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-400">
        <span>{Math.round(qa.similarity_score)}% match</span>
        {qa.session_title && (
          <>
            <span>·</span>
            <span className="truncate">{qa.session_title}</span>
          </>
        )}
      </div>
    </div>
  );
}

function HistoryIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  );
}
