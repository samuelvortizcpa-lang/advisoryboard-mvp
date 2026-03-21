"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SigningFormData {
  valid: boolean;
  client_name: string | null;
  preparer_name: string | null;
  preparer_firm: string | null;
  consent_purpose: string;
  expired: boolean;
  already_signed: boolean;
}

type PageState =
  | { kind: "loading" }
  | { kind: "error"; type: "expired" | "invalid" | "already_signed" }
  | { kind: "form"; data: SigningFormData }
  | { kind: "success" };

export default function ConsentSignPage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [agreed, setAgreed] = useState(false);
  const [typedName, setTypedName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetch(`${API_URL}/api/consent/sign/${token}`)
      .then((r) => r.json())
      .then((data: SigningFormData) => {
        if (!data.valid) {
          if (data.already_signed) {
            setState({ kind: "error", type: "already_signed" });
          } else if (data.expired) {
            setState({ kind: "error", type: "expired" });
          } else {
            setState({ kind: "error", type: "invalid" });
          }
          return;
        }
        setState({ kind: "form", data });
      })
      .catch(() => setState({ kind: "error", type: "invalid" }));
  }, [token]);

  const handleSubmit = useCallback(async () => {
    if (!token || submitting) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/consent/sign/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ typed_name: typedName, agreed }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Failed to submit consent");
      }
      setState({ kind: "success" });
    } catch (e: any) {
      setSubmitError(e.message || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }, [token, typedName, agreed, submitting]);

  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const canSubmit = agreed && typedName.trim().length >= 2 && !submitting;

  // ── Loading ──────────────────────────────────────────────────────────
  if (state.kind === "loading") {
    return (
      <Shell>
        <div className="flex items-center justify-center py-24">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
        </div>
      </Shell>
    );
  }

  // ── Error states ─────────────────────────────────────────────────────
  if (state.kind === "error") {
    const messages = {
      expired:
        "This consent link has expired. Please contact your tax professional to request a new one.",
      invalid:
        "This link is not valid. Please check your email for the correct link.",
      already_signed:
        "This consent form has already been signed. No further action is needed.",
    };
    const icons = {
      expired: (
        <svg className="mx-auto h-16 w-16 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      ),
      invalid: (
        <svg className="mx-auto h-16 w-16 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
        </svg>
      ),
      already_signed: (
        <svg className="mx-auto h-16 w-16 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      ),
    };
    return (
      <Shell>
        <div className="py-16 text-center">
          {icons[state.type]}
          <p className="mt-6 text-lg text-gray-700">{messages[state.type]}</p>
        </div>
      </Shell>
    );
  }

  // ── Success ──────────────────────────────────────────────────────────
  if (state.kind === "success") {
    return (
      <Shell>
        <div className="py-16 text-center">
          <svg className="mx-auto h-20 w-20 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
          <h2 className="mt-6 text-2xl font-semibold text-gray-900">
            Consent form signed successfully
          </h2>
          <p className="mt-3 text-gray-600">
            Your consent has been recorded. You may close this page.
          </p>
        </div>
      </Shell>
    );
  }

  // ── Form ─────────────────────────────────────────────────────────────
  const { data } = state;
  const preparerLabel = data.preparer_firm
    ? `${data.preparer_name} (${data.preparer_firm})`
    : data.preparer_name;

  return (
    <Shell>
      {/* Context */}
      <p className="mb-8 text-gray-700" style={{ fontFamily: "var(--font-sans)" }}>
        <strong>{preparerLabel}</strong> is requesting your consent to use your
        tax return information within their secure document management platform.
      </p>

      {/* Consent text */}
      <div className="mb-8 max-h-[400px] overflow-y-auto rounded-lg border border-gray-300 bg-gray-50 p-6">
        <div className="space-y-5 text-sm leading-relaxed text-gray-800" style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}>
          <p className="font-semibold">
            Consent to Disclose Tax Return Information
          </p>

          <p>
            Federal law requires this consent form be provided to you. Unless
            authorized by law, we cannot disclose your tax return information to
            third parties for purposes other than the preparation and filing of
            your tax return without your consent. If you consent to the
            disclosure of your tax return information, Federal law may not
            protect your tax return information from further use or distribution.
          </p>

          <p>
            You are not required to complete this form. If you do not sign this
            consent form, your tax return preparer will not disclose your tax
            return information to AdvisoryBoard for the purposes described below.
          </p>

          <p>
            <strong>Purpose of Disclosure:</strong> Your tax return preparer
            requests consent to disclose and use your tax return information
            within AdvisoryBoard, a secure cloud-based document intelligence
            platform, for the following purposes: AI-powered document analysis to
            assist in tax preparation and planning, automated identification of
            action items and deadlines, client brief generation for meeting
            preparation, and question-answering with source document citations.
          </p>

          <p>
            <strong>Recipient:</strong> AdvisoryBoard (myadvisoryboard.space)
          </p>

          <p>
            <strong>Duration:</strong> This consent is valid for one (1) year
            from the date of your signature.
          </p>

          <p>
            <strong>Your Rights:</strong> If you believe your tax return
            information has been disclosed or used improperly, you may contact
            the Treasury Inspector General for Tax Administration (TIGTA) by
            telephone at 1-800-366-4484, or by email at
            complaints@tigta.treas.gov.
          </p>
        </div>
      </div>

      {/* Signature section */}
      <div className="space-y-6 rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="text-lg font-semibold text-gray-900">
          Electronic Signature
        </h3>

        {/* Checkbox */}
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            className="mt-0.5 h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-gray-700">
            I have read and understand the consent form above
          </span>
        </label>

        {/* Typed name */}
        <div>
          <label
            htmlFor="typed-name"
            className="mb-1.5 block text-sm font-medium text-gray-700"
          >
            Type your full legal name as your electronic signature
          </label>
          <input
            id="typed-name"
            type="text"
            value={typedName}
            onChange={(e) => setTypedName(e.target.value)}
            placeholder="e.g. John A. Smith"
            className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          {/* Cursive preview */}
          {typedName.trim() && (
            <p
              className="mt-3 text-3xl text-gray-800"
              style={{ fontFamily: "'Dancing Script', cursive" }}
            >
              {typedName}
            </p>
          )}
        </div>

        {/* Date */}
        <div>
          <span className="block text-sm font-medium text-gray-700">Date</span>
          <span className="text-sm text-gray-600">{today}</span>
        </div>

        {/* Submit */}
        {submitError && (
          <p className="rounded-md bg-red-50 px-4 py-2 text-sm text-red-700">
            {submitError}
          </p>
        )}

        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="w-full rounded-lg bg-green-600 px-6 py-3 text-base font-semibold text-white shadow-sm transition hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Signing..." : "Sign Consent Form"}
        </button>

        <p className="text-center text-xs text-gray-500">
          By clicking &ldquo;Sign Consent Form&rdquo;, you are providing your
          electronic signature, which has the same legal effect as a handwritten
          signature.
        </p>
      </div>
    </Shell>
  );
}

/* ── Shell wrapper ─────────────────────────────────────────────────────── */

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* Google Font for cursive signature preview */}
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <link
        href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@400;700&display=swap"
        rel="stylesheet"
      />
      <div className="min-h-screen bg-gray-50">
        <div className="mx-auto max-w-[720px] px-4 py-8 sm:py-12">
          {/* Header */}
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
              AdvisoryBoard
            </h1>
            <p className="mt-2 text-base text-gray-600 sm:text-lg">
              Consent to Disclose Tax Return Information
            </p>
            <div className="mx-auto mt-4 h-px w-16 bg-blue-600" />
          </div>

          {/* Content card */}
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200 sm:p-10">
            {children}
          </div>

          {/* Footer */}
          <p className="mt-8 text-center text-xs text-gray-400">
            Powered by AdvisoryBoard &middot; myadvisoryboard.space
          </p>
        </div>
      </div>
    </>
  );
}
