"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useEffect, useRef, useState } from "react";

import { RagSource, RagStatus, createRagApi } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: RagSource[];
  confidence_tier?: "high" | "medium" | "low";
  confidence_score?: number;
  error?: boolean;
}

interface Props {
  clientId: string;
  /** Pass the current doc list length so the status banner re-fetches when docs change */
  documentCount: number;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ClientChat({ clientId, documentCount }: Props) {
  const { getToken } = useAuth();

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

  const bottomRef = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    loadHistory();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

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

    try {
      const response = await createRagApi(getToken).chat(clientId, question);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          confidence_tier: response.confidence_tier,
          confidence_score: response.confidence_score,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: err instanceof Error ? err.message : "Something went wrong.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }

  // ── Export ─────────────────────────────────────────────────────────────────

  async function handleExport(format: "txt" | "pdf") {
    setExportingFormat(format);
    try {
      await createRagApi(getToken).exportChat(clientId, format);
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
      <div className="flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">

        {/* ── Status banner ─────────────────────────────────────────────── */}
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

        {/* ── Export / Clear toolbar (only when messages exist) ─────────── */}
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
            >
              {exportingFormat === "pdf" ? "Exporting…" : "Export PDF"}
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

        {/* ── Message list ──────────────────────────────────────────────── */}
        <div className="flex min-h-[300px] max-h-[480px] flex-col gap-4 overflow-y-auto p-4">
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
              <button onClick={loadHistory} className="text-red-500 underline text-xs">Retry</button>
            </div>
          ) : messages.length === 0 ? (
            <EmptyState hasDocuments={hasProcessed ?? false} />
          ) : (
            messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
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

        {/* ── Input ─────────────────────────────────────────────────────── */}
        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-2 border-t border-gray-100 p-3"
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
    </span>
  );
}

function SourceCard({ source }: { source: RagSource }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <button
      type="button"
      onClick={() => setExpanded(!expanded)}
      className="w-full text-left rounded-lg border border-gray-200 bg-white px-3 py-2 transition-colors hover:border-gray-300 hover:bg-gray-50"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <DocIcon />
          <span className="truncate text-xs font-medium text-gray-700">{source.filename}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs font-medium ${source.score >= 70 ? "text-green-600" : source.score >= 50 ? "text-amber-600" : "text-red-500"}`}>
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

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex items-end gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {isUser ? <UserAvatar /> : <BotAvatar />}

      <div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1.5`}>
        {/* Confidence badge for assistant messages */}
        {!isUser && message.confidence_tier && (
          <ConfidenceBadge tier={message.confidence_tier} score={message.confidence_score ?? 0} />
        )}

        <div
          className={[
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
            isUser
              ? "rounded-br-sm bg-blue-600 text-white"
              : message.error
              ? "rounded-bl-sm border border-red-200 bg-red-50 text-red-700"
              : "rounded-bl-sm bg-gray-100 text-gray-800",
          ].join(" ")}
        >
          {message.content}
        </div>

        {/* Source cards */}
        {message.sources && message.sources.length > 0 && (
          <div className="flex w-full flex-col gap-1.5">
            {message.sources.map((src, idx) => (
              <SourceCard key={`${src.document_id}-${src.chunk_index}-${idx}`} source={src} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ hasDocuments }: { hasDocuments: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
        <ChatIcon className="h-6 w-6 text-blue-600" />
      </div>
      <p className="text-sm font-medium text-gray-700">No conversation yet — ask a question to get started</p>
      <p className="mt-1 max-w-xs text-xs text-gray-400">
        {hasDocuments
          ? "Questions are answered using the client's uploaded documents."
          : "Upload and process documents first, then ask questions about financials, filings, and more."}
      </p>
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
