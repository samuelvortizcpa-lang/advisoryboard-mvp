"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { RagSource, RagStatus, createRagApi, createSessionsApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import HelpTooltip from "@/components/ui/HelpTooltip";
import ChatSidebar from "./ChatSidebar";
import MarkdownContent from "./MarkdownContent";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: RagSource[];
  confidence_tier?: "high" | "medium" | "low";
  confidence_score?: number;
  analysis_tier?: string | null;
  query_type?: string;
  quota_warning_message?: string | null;
  error?: boolean;
}

interface Props {
  clientId: string;
  clientName?: string;
  /** Pass the current doc list length so the status banner re-fetches when docs change */
  documentCount: number;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ClientChat({ clientId, clientName, documentCount }: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [messages, setMessages] = useState<Message[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const [status, setStatus] = useState<RagStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [processing, setProcessing] = useState(false);

  const [exportingFormat, setExportingFormat] = useState<"txt" | "pdf" | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);

  const [imageModal, setImageModal] = useState<{
    url: string;
    filename: string;
    pageNumber: number;
  } | null>(null);

  // Session sidebar state
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeSessionTitle, setActiveSessionTitle] = useState<string | null>(null);
  const [activeSessionEndedAt, setActiveSessionEndedAt] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [fading, setFading] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const messageAreaRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Load persisted history on mount ────────────────────────────────────────

  function loadHistory() {
    setHistoryLoading(true);
    setHistoryError(null);
    createRagApi(getToken)
      .getChatHistory(clientId)
      .then((res) => {
        setMessages(
          res.messages.map((m) => ({
            role: m.role,
            content: m.content,
            sources: m.sources ?? undefined,
          }))
        );
      })
      .catch((e: Error) => {
        setHistoryError(e.message ?? "Failed to load chat history");
      })
      .finally(() => setHistoryLoading(false));
  }

  // On mount, find the active session and load its messages
  const initSession = useCallback(async () => {
    try {
      const api = createSessionsApi(getToken, activeOrg?.id);
      const res = await api.getClientSessions(clientId, 1, 10);
      const active = res.sessions.find((s) => s.ended_at === null);
      if (active) {
        setActiveSessionId(active.id);
        loadSessionMessages(active.id);
      } else {
        // No active session — start with empty state
        setMessages([]);
        setHistoryLoading(false);
      }
    } catch {
      // Fall back to loading all history
      loadHistory();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, activeOrg?.id]);

  useEffect(() => {
    initSession();
  }, [initSession]);

  // ── Load messages for a specific session ─────────────────────────────────

  async function loadSessionMessages(sessionId: string) {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const api = createSessionsApi(getToken, activeOrg?.id);
      const res = await api.getSessionMessages(sessionId);
      setActiveSessionTitle(res.title);
      setActiveSessionEndedAt(res.ended_at);
      setMessages(
        res.messages.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
          sources: (m.sources as unknown as RagSource[]) ?? undefined,
        }))
      );
      // Scroll to bottom instantly on session load
      setTimeout(() => {
        if (messageAreaRef.current) {
          messageAreaRef.current.scrollTop = messageAreaRef.current.scrollHeight;
        }
      }, 0);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load session";
      setHistoryError(msg);
    } finally {
      setHistoryLoading(false);
    }
  }

  // ── Session switching handlers ───────────────────────────────────────────

  function handleSessionSelect(sessionId: string) {
    setFading(true);
    setTimeout(() => {
      setActiveSessionId(sessionId);
      loadSessionMessages(sessionId);
      setFading(false);
    }, 150);
  }

  async function handleNewChat() {
    setFading(true);
    try {
      const api = createSessionsApi(getToken, activeOrg?.id);
      await api.closeActiveSession(clientId);
    } catch {
      // non-fatal — session may already be closed
    }
    setTimeout(() => {
      setActiveSessionId(null);
      setActiveSessionTitle(null);
      setActiveSessionEndedAt(null);
      setMessages([]);
      setRefreshTrigger((n) => n + 1);
      setFading(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }, 150);
  }

  // ── Fetch processing status ────────────────────────────────────────────────

  async function fetchStatus() {
    try {
      const s = await createRagApi(getToken).status(clientId);
      setStatus(s);
    } catch {
      // non-fatal
    } finally {
      setStatusLoading(false);
    }
  }

  useEffect(() => {
    fetchStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, documentCount]);

  // Poll while documents are pending
  useEffect(() => {
    if (!status) return;
    if (status.pending === 0) return;
    const interval = setInterval(fetchStatus, 4_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.pending]);

  // ── Auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Keyboard shortcut: Cmd/Ctrl+Shift+N for New Chat ─────────────────────

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "N") {
        e.preventDefault();
        handleNewChat();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, activeOrg?.id]);

  // ── Process documents ──────────────────────────────────────────────────────

  async function handleProcess() {
    setProcessing(true);
    try {
      await createRagApi(getToken).processAll(clientId);
      await fetchStatus();
    } catch (err) {
      console.error("Processing failed:", err);
    } finally {
      setProcessing(false);
    }
  }

  // ── Send message ───────────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    // Add a placeholder assistant message for streaming
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "" },
    ]);

    try {
      await createRagApi(getToken).chatStream(
        clientId,
        question,
        // onToken — append each token to the streaming message
        (token: string) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === "assistant") {
              updated[updated.length - 1] = { ...last, content: last.content + token };
            }
            return updated;
          });
        },
        // onDone — finalize with sources and metadata
        (meta) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === "assistant") {
              updated[updated.length - 1] = {
                ...last,
                sources: meta.sources,
                confidence_tier: meta.confidence_tier as "high" | "medium" | "low",
                confidence_score: meta.confidence_score,
                analysis_tier: meta.analysis_tier,
                query_type: meta.query_type,
                quota_warning_message: meta.quota_warning_message,
              };
            }
            return updated;
          });
          // Capture session_id from response and refresh sidebar
          if (meta.session_id) {
            setActiveSessionId(meta.session_id);
            setActiveSessionEndedAt(null); // it's active
          }
          setRefreshTrigger((n) => n + 1);
        },
      );
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && !last.content) {
          // Replace empty streaming placeholder with error
          updated[updated.length - 1] = {
            role: "assistant",
            content: err instanceof Error ? err.message : "Something went wrong.",
            error: true,
          };
        } else {
          updated.push({
            role: "assistant",
            content: err instanceof Error ? err.message : "Something went wrong.",
            error: true,
          });
        }
        return updated;
      });
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }

  // ── Export ─────────────────────────────────────────────────────────────────

  async function handleExport(format: "txt" | "pdf") {
    setExportingFormat(format);
    try {
      if (format === "pdf" && activeSessionId) {
        await createSessionsApi(getToken, activeOrg?.id).exportSessionPdf(clientId, activeSessionId);
      } else {
        await createRagApi(getToken).exportChat(clientId, format);
      }
    } catch (err) {
      console.error("Export failed:", err);
    } finally {
      setExportingFormat(null);
    }
  }

  // ── Clear history ──────────────────────────────────────────────────────────

  async function handleClearHistory() {
    setClearing(true);
    try {
      await createRagApi(getToken).clearChatHistory(clientId);
      setMessages([]);
      setShowClearConfirm(false);
    } catch (err) {
      console.error("Clear failed:", err);
    } finally {
      setClearing(false);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const hasProcessed = status && status.processed > 0;
  const hasPending = status && status.pending > 0;
  const hasErrors = status && status.errors > 0;
  const hasMessages = messages.length > 0;

  return (
    <>
      <div className="flex h-[600px] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {/* ── Sidebar ──────────────────────────────────────────────────── */}
        <ChatSidebar
          clientId={clientId}
          activeSessionId={activeSessionId}
          onSessionSelect={handleSessionSelect}
          onNewChat={handleNewChat}
          onExportSession={async (sessionId) => {
            try {
              await createSessionsApi(getToken, activeOrg?.id).exportSessionPdf(clientId, sessionId);
            } catch (err) {
              console.error("Export failed:", err);
            }
          }}
          onDeleteSession={(sessionId) => {
            if (sessionId === activeSessionId) {
              setActiveSessionId(null);
              setActiveSessionTitle(null);
              setActiveSessionEndedAt(null);
              setMessages([]);
            }
          }}
          refreshTrigger={refreshTrigger}
        />

        {/* ── Main chat area ───────────────────────────────────────────── */}
        <div className="flex min-w-0 flex-1 flex-col">

          {/* ── Session header ─────────────────────────────────────────── */}
          {activeSessionId && activeSessionEndedAt && activeSessionTitle && (
            <div className="flex items-center gap-2 border-b border-gray-100 bg-gray-50/80 px-4 py-1.5 text-xs text-gray-500">
              <span>&#128203;</span>
              <span className="font-medium text-gray-700">{activeSessionTitle}</span>
              <span className="text-gray-400">&mdash;</span>
              <span>{new Date(activeSessionEndedAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>
            </div>
          )}
          {!activeSessionId && messages.length === 0 && !historyLoading && (
            <div className="border-b border-gray-100 bg-gray-50/50 px-4 py-1.5 text-xs text-gray-400">
              New conversation
            </div>
          )}

          {/* ── Status banner ─────────────────────────────────────────── */}
          {!statusLoading && status && (
            <div className={[
              "flex items-center justify-between gap-3 border-b px-4 py-2.5 text-xs",
              hasPending
                ? "border-amber-200 bg-amber-50 text-amber-800"
                : hasErrors && !hasProcessed
                ? "border-red-200 bg-red-50 text-red-800"
                : "border-gray-100 bg-gray-50 text-gray-600",
            ].join(" ")}>
              <div className="flex items-center gap-2">
                {hasPending ? (
                  <>
                    <Spinner className="text-amber-600" />
                    <span>
                      Processing {status.pending} document{status.pending !== 1 ? "s" : ""}…
                    </span>
                  </>
                ) : hasErrors && !hasProcessed ? (
                  <>
                    <ErrorIcon />
                    <span>
                      {status.errors} document{status.errors !== 1 ? "s" : ""} failed to process.
                    </span>
                  </>
                ) : (
                  <>
                    <CheckIcon />
                    <span>
                      {status.processed} document{status.processed !== 1 ? "s" : ""} ready
                      {status.total_chunks > 0 && ` · ${status.total_chunks.toLocaleString()} chunks indexed`}
                    </span>
                  </>
                )}
              </div>

              {status.pending > 0 || (status.total_documents > 0 && status.processed < status.total_documents) ? (
                <button
                  onClick={handleProcess}
                  disabled={processing || hasPending === true}
                  className="rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {processing ? "Queuing…" : "Process Documents"}
                </button>
              ) : null}
            </div>
          )}

          {/* ── Export / Clear toolbar (only when messages exist) ─────── */}
          {!historyLoading && hasMessages && (
            <div className="flex items-center gap-3 border-b border-gray-100 bg-gray-50/60 px-4 py-1.5">
              <span className="mr-auto text-xs text-gray-400">
                {messages.length} message{messages.length !== 1 ? "s" : ""}
              </span>
              <button
                onClick={() => handleExport("txt")}
                disabled={exportingFormat !== null}
                className="text-xs text-gray-500 hover:text-gray-800 disabled:opacity-40 transition-colors"
              >
                {exportingFormat === "txt" ? "Exporting…" : "Export TXT"}
              </button>
              <span className="select-none text-gray-300">|</span>
              <button
                onClick={() => handleExport("pdf")}
                disabled={exportingFormat !== null}
                className="text-xs text-gray-500 hover:text-gray-800 disabled:opacity-40 transition-colors"
                title={activeSessionId ? "Download this conversation as PDF" : "Export all chat history as PDF"}
              >
                {exportingFormat === "pdf" ? "Exporting…" : activeSessionId ? "Export Session PDF" : "Export PDF"}
              </button>
              <span className="select-none text-gray-300">|</span>
              <button
                onClick={() => setShowClearConfirm(true)}
                className="text-xs text-red-400 hover:text-red-600 transition-colors"
              >
                Clear History
              </button>
            </div>
          )}

          {/* ── Message list ──────────────────────────────────────────── */}
          <div ref={messageAreaRef} className={`flex flex-1 flex-col gap-4 overflow-y-auto p-4 transition-opacity duration-150 ${fading ? "opacity-0" : "opacity-100"}`}>
            {historyLoading ? (
              <div className="flex flex-1 items-center justify-center py-8 text-gray-400">
                <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Loading...
              </div>
            ) : historyError ? (
              <div className="flex items-center justify-between px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
                <span>{historyError}</span>
                <button onClick={() => activeSessionId ? loadSessionMessages(activeSessionId) : loadHistory()} className="text-red-500 underline text-xs">Retry</button>
              </div>
            ) : messages.length === 0 ? (
              <EmptyState hasDocuments={hasProcessed ?? false} clientName={clientName} documentCount={documentCount} />
            ) : (
              messages.map((msg, i) => (
                <MessageBubble
                  key={i}
                  message={msg}
                  onImageClick={(url, filename, pageNumber) =>
                    setImageModal({ url, filename, pageNumber })
                  }
                />
              ))
            )}

            {/* Typing indicator */}
            {loading && (
              <div className="flex items-end gap-2">
                <BotAvatar />
                <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-gray-100 px-4 py-3">
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* ── Input ──────────────────────────────────────────────────── */}
          <div className="border-t border-gray-100">
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 px-3 pb-3 pt-1.5"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about this client's documents…"
              disabled={loading || historyLoading}
              className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading || historyLoading}
              className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Send"
            >
              <SendIcon />
            </button>
          </form>
          </div>
        </div>
      </div>

      {/* ── Clear history confirmation modal ──────────────────────────────── */}
      {showClearConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">
              Clear chat history?
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              This will permanently delete all {messages.length} chat message
              {messages.length !== 1 ? "s" : ""} for this client. This cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowClearConfirm(false)}
                disabled={clearing}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleClearHistory}
                disabled={clearing}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {clearing ? (
                  <>
                    <ClearSpinner />
                    Clearing…
                  </>
                ) : (
                  "Clear History"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Page image lightbox modal ──────────────────────────────────────── */}
      {imageModal && (
        <PageImageModal
          url={imageModal.url}
          filename={imageModal.filename}
          pageNumber={imageModal.pageNumber}
          onClose={() => setImageModal(null)}
        />
      )}
    </>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ConfidenceBadge({ tier, score }: { tier: string; score: number }) {
  const config = {
    high: { color: "bg-green-500", textColor: "text-green-700", bgColor: "bg-green-50", borderColor: "border-green-200", label: "High" },
    medium: { color: "bg-amber-500", textColor: "text-amber-700", bgColor: "bg-amber-50", borderColor: "border-amber-200", label: "Medium" },
    low: { color: "bg-red-400", textColor: "text-red-700", bgColor: "bg-red-50", borderColor: "border-red-200", label: "Low" },
  }[tier] ?? { color: "bg-gray-400", textColor: "text-gray-700", bgColor: "bg-gray-50", borderColor: "border-gray-200", label: "Unknown" };

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border ${config.borderColor} ${config.bgColor} px-2 py-0.5 text-xs font-medium ${config.textColor}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${config.color}`} />
      {config.label} · {Math.round(score)}%
      <HelpTooltip content="How confident the AI is in its answer based on the relevance of your uploaded documents. Higher confidence means better source material was found." position="right" maxWidth={260} />
    </span>
  );
}

function SourceCard({
  source,
  onImageClick,
}: {
  source: RagSource;
  onImageClick?: (url: string, filename: string, pageNumber: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasImage = Boolean(source.image_url);
  const isPdf = source.filename.toLowerCase().endsWith(".pdf");

  const scoreColor =
    source.score >= 70
      ? "text-green-600"
      : source.score >= 50
      ? "text-amber-600"
      : "text-red-500";

  // PDF source card with real thumbnail — clickable to open lightbox
  if (isPdf && hasImage) {
    return (
      <button
        type="button"
        onClick={() =>
          onImageClick?.(source.image_url!, source.filename, source.page_number ?? 1)
        }
        className="flex w-full items-center gap-3 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-left transition-colors hover:border-blue-300 hover:bg-blue-50/40"
      >
        <div className="h-[52px] w-[40px] flex-shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-100">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={source.image_url}
            alt={`PDF Page ${source.page_number}`}
            className="h-full w-full object-cover object-top"
          />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-xs font-medium text-gray-700">
            {source.filename}
          </span>
          <span className="text-[10px] text-gray-400">
            PDF Page {source.page_number} — click to view
          </span>
        </div>
        <span className={`flex-shrink-0 text-xs font-medium ${scoreColor}`}>
          {Math.round(source.score)}%
        </span>
      </button>
    );
  }

  // PDF source card WITHOUT image — placeholder thumbnail
  if (isPdf && !hasImage) {
    return (
      <div
        className="flex w-full items-center gap-3 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-left"
        title="Re-process this document to enable page preview"
      >
        <div className="flex h-[52px] w-[40px] flex-shrink-0 flex-col items-center justify-center rounded border border-gray-200 bg-gray-100">
          <PdfPlaceholderIcon />
          <span className="mt-0.5 text-[7px] leading-none text-gray-400">
            No preview
          </span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-xs font-medium text-gray-700">
            {source.filename}
          </span>
          <span className="text-[10px] text-gray-400">
            {source.page_number != null
              ? `PDF Page ${source.page_number}`
              : "Re-process to enable preview"}
          </span>
        </div>
        <span className={`flex-shrink-0 text-xs font-medium ${scoreColor}`}>
          {Math.round(source.score)}%
        </span>
      </div>
    );
  }

  // Non-PDF source card — text-based with expandable preview
  return (
    <button
      type="button"
      onClick={() => setExpanded(!expanded)}
      className="w-full text-left rounded-lg border border-gray-200 bg-white px-3 py-2 transition-colors hover:border-gray-300 hover:bg-gray-50"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <DocIcon />
          <span className="truncate text-xs font-medium text-gray-700">
            {source.filename}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs font-medium ${scoreColor}`}>
            {Math.round(source.score)}%
          </span>
          <svg
            className={`h-3 w-3 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {!expanded && (
        <p className="mt-1 truncate text-xs text-gray-400">{source.chunk_text}</p>
      )}
      {expanded && (
        <p className="mt-1.5 text-xs leading-relaxed text-gray-600 whitespace-pre-wrap">{source.chunk_text}</p>
      )}
    </button>
  );
}

function MessageBubble({
  message,
  onImageClick,
}: {
  message: Message;
  onImageClick?: (url: string, filename: string, pageNumber: number) => void;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex items-end gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {isUser ? <UserAvatar /> : <BotAvatar />}

      <div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1.5`}>
        {/* Confidence badge + model indicator for assistant messages */}
        {!isUser && message.confidence_tier && (
          <ConfidenceBadge tier={message.confidence_tier} score={message.confidence_score ?? 0} />
        )}
        {!isUser && message.analysis_tier && message.analysis_tier !== "standard" && (
          <span className="inline-flex items-center gap-1 text-[10px] text-gray-400">
            <span className={`h-1.5 w-1.5 rounded-full ${
              message.analysis_tier === "premium" ? "bg-purple-400" : "bg-blue-400"
            }`} />
            {message.analysis_tier === "premium" ? "Premium analysis" : "Advanced analysis"}
          </span>
        )}

        <div
          className={[
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-br-sm bg-blue-600 text-white whitespace-pre-wrap"
              : message.error
              ? "rounded-bl-sm border border-red-200 bg-red-50 text-red-700 whitespace-pre-wrap"
              : "rounded-bl-sm bg-gray-100 text-gray-800",
          ].join(" ")}
        >
          {isUser || message.error ? (
            message.content
          ) : (
            <MarkdownContent content={message.content} />
          )}
        </div>

        {/* Source cards */}
        {message.sources && message.sources.length > 0 && (
          <div className="flex w-full flex-col gap-1.5">
            {message.sources.map((src, idx) => (
              <SourceCard
                key={`${src.document_id}-${src.page_number ?? src.chunk_index}-${idx}`}
                source={src}
                onImageClick={onImageClick}
              />
            ))}
          </div>
        )}

        {/* Quota warning */}
        {!isUser && message.quota_warning_message && (
          <div className={`w-full rounded-lg px-3 py-1.5 text-xs ${
            message.quota_warning_message.includes("limit reached") || message.quota_warning_message.includes("does not include")
              ? "border border-red-200 bg-red-50 text-red-600"
              : "border border-amber-200 bg-amber-50 text-amber-700"
          }`}>
            {message.quota_warning_message}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ hasDocuments, clientName, documentCount }: { hasDocuments: boolean; clientName?: string; documentCount: number }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-blue-50">
        <ChatIcon className="h-7 w-7 text-blue-600" />
      </div>
      <p className="text-sm font-medium text-gray-700">
        {clientName
          ? `Ask me anything about ${clientName}\u2019s documents`
          : "Ask a question to get started"}
      </p>
      <p className="mt-1.5 max-w-xs text-xs text-gray-400">
        {hasDocuments
          ? `${documentCount} document${documentCount !== 1 ? "s" : ""} indexed and ready for questions about financials, filings, and more.`
          : "Upload and process documents first, then ask questions about financials, filings, and more."}
      </p>
      {hasDocuments && (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {["Summarize recent filings", "Key financial changes", "Open action items"].map((q) => (
            <span key={q} className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-500">
              {q}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function PageImageModal({
  url,
  filename,
  pageNumber,
  onClose,
}: {
  url: string;
  filename: string;
  pageNumber: number;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] max-w-[90vw] flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-2 flex w-full items-center justify-between">
          <span className="text-sm font-medium text-white">
            {filename} — PDF Page {pageNumber}
          </span>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20"
            aria-label="Close"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Image */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={`PDF Page ${pageNumber} of ${filename}`}
          className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
        />
      </div>
    </div>
  );
}

function BotAvatar() {
  return (
    <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold">
      AI
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gray-200 text-gray-600 text-xs font-bold">
      You
    </div>
  );
}

function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`h-3 w-3 rounded-full border-2 border-current border-t-transparent animate-spin ${className}`}
    />
  );
}

function ClearSpinner() {
  return (
    <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
  );
}

function CheckIcon() {
  return (
    <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg className="h-3 w-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function PdfPlaceholderIcon() {
  return (
    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  );
}

function ChatIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
    </svg>
  );
}
