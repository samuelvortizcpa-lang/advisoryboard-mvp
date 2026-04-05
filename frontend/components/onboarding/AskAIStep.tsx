"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

import { ChatApiResponse, createRagApi } from "@/lib/api";

interface Props {
  onNext: () => void;
  onSkip: () => void;
  clientId: string | null;
  clientName: string | null;
  documentId: string | null;
}

const SUGGESTIONS = [
  "What type of document is this?",
  "Summarize the key details",
  "Are there any action items I should note?",
];

export default function AskAIStep({
  onNext,
  onSkip,
  clientId,
  clientName,
}: Props) {
  const { getToken } = useAuth();

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [response, setResponse] = useState<ChatApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // No client — can't query
  if (!clientId) {
    return (
      <div className="w-full max-w-lg text-center">
        <p className="text-xs font-medium uppercase tracking-widest text-gray-400">
          Step 3 of 3
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-gray-900">
          Ask your first question
        </h2>
        <p className="mt-2 text-sm text-gray-500">
          Upload a document first to try the AI.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            onClick={onSkip}
            className="rounded-lg bg-gray-900 px-8 py-3 text-sm font-medium text-white transition hover:bg-gray-800"
          >
            Skip to finish
          </button>
        </div>
      </div>
    );
  }

  async function handleAsk() {
    if (!question.trim() || !clientId) return;
    setAsking(true);
    setError(null);
    setResponse(null);

    try {
      const api = createRagApi(getToken);
      const result = await api.chat(clientId, question.trim());
      setResponse(result);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Something went wrong. Please try again."
      );
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="w-full max-w-lg">
      <p className="text-xs font-medium uppercase tracking-widest text-gray-400">
        Step 3 of 3
      </p>
      <h2 className="mt-2 text-2xl font-semibold text-gray-900">
        Ask your first question
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        Try asking something about {clientName || "your documents"}. Callwen
        will search across all uploaded files and give you a source-cited answer.
      </p>

      {/* Chat input */}
      <div className="mt-6">
        <textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleAsk();
            }
          }}
          placeholder="e.g., What was the total income on this return?"
          disabled={asking}
          className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-gray-900 disabled:opacity-50"
        />

        <button
          onClick={handleAsk}
          disabled={asking || !question.trim()}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 py-3 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {asking ? (
            <>
              <ThinkingDots />
              Thinking…
            </>
          ) : (
            "Ask Callwen \u2192"
          )}
        </button>
      </div>

      {/* Suggestions */}
      {!response && !asking && (
        <div className="mt-3">
          <p className="text-xs text-gray-400">Try one of these:</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => setQuestion(s)}
                className="rounded-full bg-gray-100 px-3 py-1.5 text-xs text-gray-600 transition hover:bg-gray-200"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {/* AI Response */}
      {response && (
        <div className="mt-4 rounded-lg bg-gray-50 p-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
            {response.answer}
          </p>

          {response.sources.length > 0 && (
            <div className="mt-3 border-t border-gray-200 pt-3">
              <p className="text-xs font-medium text-gray-500">Sources</p>
              <div className="mt-1 space-y-1">
                {response.sources.map((src, i) => (
                  <p key={i} className="text-xs text-gray-400">
                    {src.filename}
                    {src.page_number ? ` (p. ${src.page_number})` : ""}
                  </p>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={onNext}
            className="mt-4 w-full rounded-lg bg-gray-900 py-3 text-sm font-medium text-white transition hover:bg-gray-800"
          >
            Continue &rarr;
          </button>
        </div>
      )}

      {/* Skip */}
      {!response && (
        <button
          onClick={onSkip}
          disabled={asking}
          className="mt-4 w-full py-2 text-sm text-gray-500 transition-colors hover:text-gray-700 disabled:opacity-50"
        >
          Skip — I&apos;ll try this later
        </button>
      )}
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex gap-0.5">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white [animation-delay:300ms]" />
    </span>
  );
}
