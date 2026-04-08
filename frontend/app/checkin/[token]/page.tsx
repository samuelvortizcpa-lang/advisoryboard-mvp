"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CheckinQuestion {
  id: string;
  text: string;
  type: string;
  options?: string[] | null;
}

interface CheckinFormData {
  status: string;
  questions?: CheckinQuestion[] | null;
  client_name?: string | null;
  firm_name?: string | null;
  template_name?: string | null;
  completed_at?: string | null;
  message?: string | null;
}

type PageState = "loading" | "form" | "expired" | "completed" | "submitted" | "error";

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api`;

// ─── Page Component ──────────────────────────────────────────────────────────

export default function CheckinPage() {
  const { token } = useParams<{ token: string }>();

  const [state, setState] = useState<PageState>("loading");
  const [data, setData] = useState<CheckinFormData | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Fetch form data on mount
  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/checkins/public/${token}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("Not found");
        return res.json();
      })
      .then((d: CheckinFormData) => {
        setData(d);
        if (d.status === "expired") setState("expired");
        else if (d.status === "completed") setState("completed");
        else setState("form");
      })
      .catch(() => setState("error"));
  }, [token]);

  async function handleSubmit() {
    if (!token || submitting) return;
    setSubmitting(true);
    setSubmitError(null);

    const responses = Object.entries(answers)
      .filter(([, v]) => v !== "" && v !== null && v !== undefined)
      .map(([question_id, answer]) => ({ question_id, answer }));

    try {
      const res = await fetch(`${API_BASE}/checkins/public/${token}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ responses }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Submission failed");
      }
      setState("submitted");
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function setAnswer(questionId: string, value: unknown) {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (state === "loading") {
    return (
      <Shell>
        <div className="flex flex-col items-center justify-center py-20">
          <span className="block h-8 w-8 animate-spin rounded-full border-3 border-gray-300 border-t-[#5bb8af]" />
          <p className="mt-4 text-sm text-gray-500">Loading your check-in...</p>
        </div>
      </Shell>
    );
  }

  if (state === "error") {
    return (
      <Shell>
        <StatusPage
          icon={<ErrorIcon />}
          title="Check-in not found"
          subtitle="This link may be invalid. Please contact your advisor for a new link."
        />
      </Shell>
    );
  }

  if (state === "expired") {
    return (
      <Shell>
        <StatusPage
          icon={<WarningIcon />}
          title="This check-in has expired"
          subtitle="Please contact your advisor if you'd like a new link."
        />
      </Shell>
    );
  }

  if (state === "completed") {
    const completedDate = data?.completed_at
      ? new Date(data.completed_at).toLocaleDateString("en-US", {
          month: "long", day: "numeric", year: "numeric",
        })
      : null;

    return (
      <Shell>
        <StatusPage
          icon={<CheckCircleIcon />}
          title="You've already completed this check-in"
          subtitle={
            completedDate
              ? `Your responses were submitted on ${completedDate}.`
              : "Your responses have already been submitted."
          }
          footer="You can close this page."
        />
      </Shell>
    );
  }

  if (state === "submitted") {
    return (
      <Shell>
        <div className="flex flex-col items-center py-16 text-center animate-fade-in">
          <div className="animate-scale-in">
            <CheckCircleIcon />
          </div>
          <h2 className="mt-6 text-2xl font-semibold text-gray-900" style={{ fontFamily: "'Outfit', sans-serif" }}>
            Thanks{data?.client_name ? `, ${data.client_name}` : ""}!
          </h2>
          <p className="mt-2 text-gray-600">
            Your responses have been sent to {data?.firm_name ?? "your advisor"}.
          </p>
          <p className="mt-4 text-sm text-gray-400">You can close this page.</p>
        </div>
      </Shell>
    );
  }

  // ── Form state ──────────────────────────────────────────────────────────────

  const questions = data?.questions ?? [];
  const answeredCount = questions.filter((q) => {
    const a = answers[q.id];
    if (a === undefined || a === null || a === "") return false;
    if (Array.isArray(a) && a.length === 0) return false;
    return true;
  }).length;

  return (
    <Shell>
      {/* Header */}
      <div className="mb-8 text-center">
        <h2 className="text-2xl font-semibold text-gray-900 sm:text-3xl" style={{ fontFamily: "'Outfit', sans-serif" }}>
          {data?.template_name ?? "Check-in"}
        </h2>
        {(data?.client_name || data?.firm_name) && (
          <p className="mt-3 text-gray-600">
            {data?.client_name ? `Hi ${data.client_name}, p` : "P"}lease take a few minutes to answer
            these questions{data?.firm_name ? ` before your upcoming meeting with ${data.firm_name}` : ""}.
          </p>
        )}
      </div>

      {/* Progress */}
      <div className="mb-8">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{answeredCount} of {questions.length} answered</span>
          <span className="text-gray-400">All questions are optional</span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-full rounded-full bg-[#5bb8af] transition-all duration-300"
            style={{ width: `${questions.length > 0 ? (answeredCount / questions.length) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Questions */}
      <div className="space-y-5">
        {questions.map((q, i) => (
          <QuestionCard
            key={q.id}
            question={q}
            index={i}
            value={answers[q.id]}
            onChange={(v) => setAnswer(q.id, v)}
            disabled={submitting}
          />
        ))}
      </div>

      {/* Submit */}
      <div className="mt-8">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#5bb8af] px-6 py-3.5 text-base font-semibold text-white shadow-sm transition-colors hover:bg-[#4a9e96] focus:outline-none focus:ring-2 focus:ring-[#5bb8af] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? (
            <>
              <span className="block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Submitting...
            </>
          ) : (
            "Submit Check-in"
          )}
        </button>
        <p className="mt-3 text-center text-xs text-gray-400">
          All responses are optional. Your answers help your advisor prepare for your meeting.
        </p>
        {submitError && (
          <div className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-center">
            <p className="text-sm text-red-700">{submitError}</p>
            <button
              onClick={handleSubmit}
              className="mt-2 text-sm font-medium text-red-600 underline hover:text-red-800"
            >
              Try again
            </button>
          </div>
        )}
      </div>
    </Shell>
  );
}

// ─── Question Card ──────────────────────────────────────────────────────────

function QuestionCard({
  question,
  index,
  value,
  onChange,
  disabled,
}: {
  question: CheckinQuestion;
  index: number;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled: boolean;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <label className="mb-3 block text-sm font-medium text-gray-900">
        <span className="mr-2 text-gray-400">{index + 1}.</span>
        {question.text}
      </label>

      {question.type === "text" && (
        <input
          type="text"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="Your answer..."
          className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-900 placeholder-gray-400 focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af] disabled:bg-gray-50 disabled:text-gray-500"
        />
      )}

      {question.type === "textarea" && (
        <div className="relative">
          <textarea
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            rows={4}
            placeholder="Your answer..."
            className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-900 placeholder-gray-400 focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af] disabled:bg-gray-50 disabled:text-gray-500"
          />
          <span className="absolute bottom-2 right-3 text-xs text-gray-300">
            {((value as string) ?? "").length}
          </span>
        </div>
      )}

      {question.type === "rating" && (
        <RatingInput
          value={(value as number) ?? 0}
          onChange={onChange}
          disabled={disabled}
        />
      )}

      {question.type === "select" && question.options && (
        <div className="space-y-2">
          {question.options.map((opt) => (
            <label
              key={opt}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors ${
                value === opt
                  ? "border-[#5bb8af] bg-[#5bb8af]/5 text-gray-900"
                  : "border-gray-200 text-gray-700 hover:border-gray-300"
              } ${disabled ? "pointer-events-none opacity-60" : ""}`}
            >
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${
                  value === opt ? "border-[#5bb8af]" : "border-gray-300"
                }`}
              >
                {value === opt && <span className="block h-2.5 w-2.5 rounded-full bg-[#5bb8af]" />}
              </span>
              {opt}
            </label>
          ))}
        </div>
      )}

      {question.type === "multiselect" && question.options && (
        <div className="space-y-2">
          {question.options.map((opt) => {
            const selected = Array.isArray(value) && (value as string[]).includes(opt);
            return (
              <label
                key={opt}
                className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors ${
                  selected
                    ? "border-[#5bb8af] bg-[#5bb8af]/5 text-gray-900"
                    : "border-gray-200 text-gray-700 hover:border-gray-300"
                } ${disabled ? "pointer-events-none opacity-60" : ""}`}
              >
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border ${
                    selected ? "border-[#5bb8af] bg-[#5bb8af]" : "border-gray-300"
                  }`}
                >
                  {selected && (
                    <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  )}
                </span>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => {
                    const current = Array.isArray(value) ? (value as string[]) : [];
                    onChange(
                      selected ? current.filter((v) => v !== opt) : [...current, opt]
                    );
                  }}
                  disabled={disabled}
                  className="sr-only"
                />
                {opt}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Rating Input ───────────────────────────────────────────────────────────

function RatingInput({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex gap-2">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          onClick={() => onChange(value === n ? 0 : n)}
          disabled={disabled}
          className={`flex h-12 w-12 items-center justify-center rounded-lg border-2 text-base font-semibold transition-all ${
            value === n
              ? "border-[#5bb8af] bg-[#5bb8af] text-white shadow-sm"
              : "border-gray-200 text-gray-500 hover:border-[#5bb8af] hover:text-[#5bb8af]"
          } disabled:pointer-events-none disabled:opacity-60`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

// ─── Shell ──────────────────────────────────────────────────────────────────

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <link
        href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap"
        rel="stylesheet"
      />
      <div className="min-h-screen bg-white" style={{ fontFamily: "'Outfit', system-ui, sans-serif" }}>
        <div className="mx-auto max-w-[640px] px-5 py-8 sm:px-8 sm:py-12">
          {/* Logo */}
          <div className="mb-8 text-center">
            <span className="text-xl font-bold tracking-tight text-gray-900">Callwen</span>
          </div>

          {children}

          {/* Footer */}
          <p className="mt-12 text-center text-xs text-gray-300">
            Powered by Callwen
          </p>
        </div>
      </div>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
          animation: fade-in 0.4s ease-out;
        }
        @keyframes scale-in {
          from { transform: scale(0.8); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
        .animate-scale-in {
          animation: scale-in 0.5s ease-out;
        }
      `}} />
    </>
  );
}

// ─── Status Page ────────────────────────────────────────────────────────────

function StatusPage({
  icon,
  title,
  subtitle,
  footer,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  footer?: string;
}) {
  return (
    <div className="flex flex-col items-center py-16 text-center">
      {icon}
      <h2 className="mt-6 text-xl font-semibold text-gray-900" style={{ fontFamily: "'Outfit', sans-serif" }}>
        {title}
      </h2>
      <p className="mt-2 text-gray-600">{subtitle}</p>
      {footer && <p className="mt-4 text-sm text-gray-400">{footer}</p>}
    </div>
  );
}

// ─── Icons ──────────────────────────────────────────────────────────────────

function CheckCircleIcon() {
  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[#5bb8af]/10">
      <svg className="h-8 w-8 text-[#5bb8af]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    </div>
  );
}

function WarningIcon() {
  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-amber-50">
      <svg className="h-8 w-8 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
    </div>
  );
}

function ErrorIcon() {
  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-50">
      <svg className="h-8 w-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
      </svg>
    </div>
  );
}
