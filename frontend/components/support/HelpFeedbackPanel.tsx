"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useOrg } from "@/contexts/OrgContext";

// ─── Types ───────────────────────────────────────────────────────────────────

type Category = "bug" | "question" | "feature_request" | "general";

interface CategoryOption {
  value: Category;
  icon: string;
  label: string;
  description: string;
  placeholder: string;
}

const CATEGORIES: CategoryOption[] = [
  { value: "bug", icon: "🐛", label: "Report a bug", description: "Something isn't working right", placeholder: "What's not working?" },
  { value: "question", icon: "❓", label: "Ask a question", description: "How does something work?", placeholder: "What's your question?" },
  { value: "feature_request", icon: "💡", label: "Suggest a feature", description: "Ideas to improve Callwen", placeholder: "What feature would you like?" },
  { value: "general", icon: "💬", label: "General feedback", description: "Anything else on your mind", placeholder: "What's on your mind?" },
];

// ─── API ─────────────────────────────────────────────────────────────────────

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api`;

// ─── Component ───────────────────────────────────────────────────────────────

export default function HelpFeedbackPanel({ onClose }: { onClose: () => void }) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [step, setStep] = useState<"category" | "form" | "success" | "error">("category");
  const [category, setCategory] = useState<CategoryOption | null>(null);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [screenshotB64, setScreenshotB64] = useState<string | null>(null);
  const [screenshotName, setScreenshotName] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [visible, setVisible] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Slide-in on mount
  useEffect(() => {
    requestAnimationFrame(() => setVisible(true));
  }, []);

  // Auto-close after success
  useEffect(() => {
    if (step !== "success") return;
    const t = setTimeout(onClose, 3000);
    return () => clearTimeout(t);
  }, [step, onClose]);

  const handleSelectCategory = (cat: CategoryOption) => {
    setCategory(cat);
    setStep("form");
  };

  const handleBack = () => {
    setCategory(null);
    setStep("category");
  };

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      alert("Screenshot must be under 10 MB");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setScreenshotB64(reader.result as string);
      setScreenshotName(file.name);
    };
    reader.readAsDataURL(file);
  }, []);

  const handleSubmit = async () => {
    if (!category || !subject.trim() || !description.trim()) return;
    setSending(true);
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/support/tickets`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(activeOrg?.id ? { "X-Org-Id": activeOrg.id } : {}),
        },
        body: JSON.stringify({
          category: category.value,
          subject: subject.trim(),
          description: description.trim(),
          page_url: typeof window !== "undefined" ? window.location.href : null,
          screenshot_base64: screenshotB64
            ? screenshotB64.replace(/^data:image\/\w+;base64,/, "")
            : null,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setStep("success");
    } catch {
      setStep("error");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className={`absolute inset-0 bg-black/20 transition-opacity duration-200 ${visible ? "opacity-100" : "opacity-0"}`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`relative w-[400px] max-w-[90vw] h-full bg-white dark:bg-gray-900 shadow-xl flex flex-col transition-transform duration-200 ${visible ? "translate-x-0" : "translate-x-full"}`}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-gray-200 dark:border-gray-800 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Help &amp; Feedback</h2>
            <p className="mt-0.5 text-xs text-gray-500">Report a problem or suggest an improvement</p>
          </div>
          <button onClick={onClose} className="mt-0.5 rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300">
            <CloseIcon />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* ── Category selection ─── */}
          {step === "category" && (
            <div className="grid grid-cols-2 gap-3">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.value}
                  onClick={() => handleSelectCategory(cat)}
                  className="flex flex-col items-start rounded-lg border border-gray-200 p-3 text-left transition-colors hover:border-gray-400 hover:bg-gray-50 dark:border-gray-700 dark:hover:border-gray-500 dark:hover:bg-gray-800"
                >
                  <span className="text-xl">{cat.icon}</span>
                  <span className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">{cat.label}</span>
                  <span className="mt-0.5 text-xs text-gray-500">{cat.description}</span>
                </button>
              ))}
            </div>
          )}

          {/* ── Form ─── */}
          {step === "form" && category && (
            <div className="space-y-4">
              {/* Breadcrumb */}
              <button onClick={handleBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
                <BackArrow />
                <span>{category.label}</span>
              </button>

              {/* Subject */}
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder={category.placeholder}
                  maxLength={500}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none focus:ring-0 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                />
              </div>

              {/* Description */}
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe in detail..."
                  rows={6}
                  className="w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none focus:ring-0 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                />
              </div>

              {/* Screenshot */}
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="hidden"
                  onChange={handleFileChange}
                />
                {screenshotB64 ? (
                  <div className="flex items-center gap-2 rounded-lg border border-gray-200 p-2 dark:border-gray-700">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={screenshotB64} alt="Screenshot preview" className="h-12 w-12 rounded object-cover" />
                    <span className="min-w-0 flex-1 truncate text-xs text-gray-600 dark:text-gray-400">{screenshotName}</span>
                    <button
                      onClick={() => { setScreenshotB64(null); setScreenshotName(null); }}
                      className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
                    >
                      <CloseIcon />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex w-full items-center gap-2 rounded-lg border border-dashed border-gray-300 px-3 py-2 text-sm text-gray-500 transition-colors hover:border-gray-400 hover:text-gray-700 dark:border-gray-600 dark:hover:border-gray-500 dark:hover:text-gray-300"
                  >
                    <span>📎</span>
                    Attach screenshot
                  </button>
                )}
              </div>

              {/* Submit */}
              <button
                onClick={handleSubmit}
                disabled={sending || !subject.trim() || !description.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200"
              >
                {sending ? (
                  <>
                    <Spinner />
                    Sending...
                  </>
                ) : (
                  "Send feedback"
                )}
              </button>
            </div>
          )}

          {/* ── Success ─── */}
          {step === "success" && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <CheckIcon />
              </div>
              <h3 className="mt-4 text-base font-semibold text-gray-900 dark:text-gray-100">Thanks for your feedback!</h3>
              <p className="mt-1 text-sm text-gray-500">We&apos;ll get back to you shortly.</p>
              <button
                onClick={onClose}
                className="mt-6 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Done
              </button>
            </div>
          )}

          {/* ── Error ─── */}
          {step === "error" && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <ErrorIcon />
              </div>
              <h3 className="mt-4 text-base font-semibold text-gray-900 dark:text-gray-100">Something went wrong</h3>
              <p className="mt-1 text-sm text-gray-500">
                Please try again, or email us at{" "}
                <a href="mailto:support@myadvisoryboard.space" className="text-blue-600 underline">
                  support@myadvisoryboard.space
                </a>
              </p>
              <button
                onClick={() => setStep("form")}
                className="mt-6 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function CloseIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function BackArrow() {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="h-7 w-7 text-green-600 dark:text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg className="h-7 w-7 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
    </svg>
  );
}
