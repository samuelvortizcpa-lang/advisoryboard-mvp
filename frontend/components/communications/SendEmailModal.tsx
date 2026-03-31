"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import {
  ClientCommunication,
  CommunicationSendResponse,
  DraftEmailResponse,
  EmailTemplate,
  RenderedTemplate,
  createCommunicationsApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type Approach = "template" | "ai" | "scratch" | null;

interface SendEmailModalProps {
  clientId: string;
  clientName: string;
  clientEmail: string | null;
  onClose: () => void;
  onSent: () => void;
}

// ─── Follow-up options ───────────────────────────────────────────────────────

const FOLLOW_UP_OPTIONS = [
  { label: "No reminder", value: 0 },
  { label: "3 days", value: 3 },
  { label: "7 days", value: 7 },
  { label: "14 days", value: 14 },
  { label: "30 days", value: 30 },
];

// ─── Component ───────────────────────────────────────────────────────────────

export default function SendEmailModal({
  clientId,
  clientName,
  clientEmail,
  onClose,
  onSent,
}: SendEmailModalProps) {
  const { getToken } = useAuth();

  // Step state
  const [approach, setApproach] = useState<Approach>(null);
  const [showEditor, setShowEditor] = useState(false);

  // Template state
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");

  // AI draft state
  const [purpose, setPurpose] = useState("");
  const [additionalContext, setAdditionalContext] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [aiDrafted, setAiDrafted] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);

  // Email form state
  const [to, setTo] = useState(clientEmail || "");
  const [subject, setSubject] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [followUpDays, setFollowUpDays] = useState(0);
  const [templateId, setTemplateId] = useState<string | null>(null);

  // Send state
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // ── Load templates ─────────────────────────────────────────────────────────

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const res = await createCommunicationsApi(getToken).getTemplates();
      setTemplates(res);
    } catch {
      // non-fatal
    } finally {
      setTemplatesLoading(false);
    }
  }, [getToken]);

  // ── Handle approach selection ──────────────────────────────────────────────

  function selectApproach(a: Approach) {
    setApproach(a);
    if (a === "template") {
      loadTemplates();
    } else if (a === "scratch") {
      setShowEditor(true);
    }
  }

  // ── Handle template selection ──────────────────────────────────────────────

  async function handleTemplateSelect(tplId: string) {
    setSelectedTemplateId(tplId);
    if (!tplId) return;

    try {
      const rendered = await createCommunicationsApi(getToken).renderTemplate(clientId, {
        template_id: tplId,
      });
      setSubject(rendered.subject);
      setBodyHtml(rendered.body_html);
      setTemplateId(tplId);

      // Set default follow-up for meeting_request templates
      const tpl = templates.find((t) => t.id === tplId);
      if (tpl?.template_type === "meeting_request") {
        setFollowUpDays(7);
      }

      setShowEditor(true);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to render template", "error");
    }
  }

  // ── Handle AI draft ────────────────────────────────────────────────────────

  async function handleGenerateDraft() {
    if (!purpose.trim()) return;
    setDrafting(true);
    setDraftError(null);
    try {
      const draft = await createCommunicationsApi(getToken).draftWithAI(clientId, {
        purpose: purpose.trim(),
        additional_context: additionalContext.trim() || undefined,
      });
      setSubject(draft.subject);
      setBodyHtml(draft.body_html);
      setAiDrafted(true);

      // Default follow-up for meeting requests
      if (purpose.toLowerCase().includes("meeting") || purpose.toLowerCase().includes("schedule")) {
        setFollowUpDays(7);
      }

      setShowEditor(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to generate draft. Please try again.";
      setDraftError(msg);
      showToast(msg, "error");
    } finally {
      setDrafting(false);
    }
  }

  // ── Send email ─────────────────────────────────────────────────────────────

  async function handleSend() {
    if (!to.trim() || !subject.trim() || !bodyHtml.trim()) {
      showToast("Please fill in all required fields", "error");
      return;
    }

    setSending(true);
    try {
      await createCommunicationsApi(getToken).sendEmail(clientId, {
        subject: subject.trim(),
        body_html: bodyHtml,
        recipient_email: to.trim(),
        recipient_name: clientName,
        template_id: templateId || undefined,
        follow_up_days: followUpDays || undefined,
        metadata: aiDrafted ? { ai_drafted: true, purpose } : undefined,
      });
      showToast(`Email sent to ${clientName}`, "success");
      setTimeout(() => {
        onSent();
        onClose();
      }, 1200);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to send email", "error");
    } finally {
      setSending(false);
    }
  }

  // ── Toast helper ───────────────────────────────────────────────────────────

  function showToast(message: string, type: "success" | "error") {
    setToast({ message, type });
    if (type === "success") {
      setTimeout(() => setToast(null), 3000);
    } else {
      setTimeout(() => setToast(null), 5000);
    }
  }

  // ── Escape key handler ─────────────────────────────────────────────────────

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const systemTemplates = templates.filter((t) => t.is_default);
  const customTemplates = templates.filter((t) => !t.is_default);

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-white shadow-2xl animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Send Email</h2>
            <p className="text-xs text-gray-500">To {clientName}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {!showEditor ? (
            <>
              {/* Step 1: Choose approach */}
              {!approach && (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-gray-700">How would you like to compose this email?</p>
                  <button
                    onClick={() => selectApproach("template")}
                    className="group w-full rounded-xl border border-gray-200 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600 group-hover:bg-blue-100">
                        <TemplateIcon />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">Use Template</p>
                        <p className="text-xs text-gray-500">Pick a pre-built email template</p>
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => selectApproach("ai")}
                    className="group w-full rounded-xl border border-gray-200 p-4 text-left transition hover:border-purple-300 hover:bg-purple-50/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50 text-purple-600 group-hover:bg-purple-100">
                        <SparklesIcon />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">AI Draft</p>
                        <p className="text-xs text-gray-500">Describe the purpose, AI writes the email</p>
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => selectApproach("scratch")}
                    className="group w-full rounded-xl border border-gray-200 p-4 text-left transition hover:border-gray-400 hover:bg-gray-50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100 text-gray-600 group-hover:bg-gray-200">
                        <PenIcon />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">Write From Scratch</p>
                        <p className="text-xs text-gray-500">Start with a blank email</p>
                      </div>
                    </div>
                  </button>
                </div>
              )}

              {/* Template picker */}
              {approach === "template" && (
                <div className="space-y-4">
                  <button
                    onClick={() => setApproach(null)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    &larr; Back
                  </button>
                  <p className="text-sm font-medium text-gray-700">Choose a template</p>
                  {templatesLoading ? (
                    <div className="flex items-center gap-2 py-6 text-gray-400">
                      <SmallSpinner />
                      <span className="text-sm">Loading templates...</span>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {systemTemplates.length > 0 && (
                        <div>
                          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">System Templates</p>
                          <div className="space-y-2">
                            {systemTemplates.map((t) => (
                              <button
                                key={t.id}
                                onClick={() => handleTemplateSelect(t.id)}
                                className={`w-full rounded-lg border p-3 text-left transition hover:border-blue-300 hover:bg-blue-50/50 ${
                                  selectedTemplateId === t.id ? "border-blue-400 bg-blue-50" : "border-gray-200"
                                }`}
                              >
                                <p className="text-sm font-medium text-gray-900">{t.name}</p>
                                <p className="mt-0.5 text-xs text-gray-500">{t.template_type}</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      {customTemplates.length > 0 && (
                        <div>
                          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">Custom Templates</p>
                          <div className="space-y-2">
                            {customTemplates.map((t) => (
                              <button
                                key={t.id}
                                onClick={() => handleTemplateSelect(t.id)}
                                className={`w-full rounded-lg border p-3 text-left transition hover:border-blue-300 hover:bg-blue-50/50 ${
                                  selectedTemplateId === t.id ? "border-blue-400 bg-blue-50" : "border-gray-200"
                                }`}
                              >
                                <p className="text-sm font-medium text-gray-900">{t.name}</p>
                                <p className="mt-0.5 text-xs text-gray-500">{t.template_type}</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* AI draft form */}
              {approach === "ai" && (
                <div className="space-y-4">
                  <button
                    onClick={() => setApproach(null)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    &larr; Back
                  </button>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      What&apos;s this email about?
                    </label>
                    <input
                      type="text"
                      value={purpose}
                      onChange={(e) => setPurpose(e.target.value)}
                      placeholder="Schedule quarterly review, follow up on missing K-1, discuss year-end planning..."
                      className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Additional context <span className="font-normal text-gray-400">(optional)</span>
                    </label>
                    <textarea
                      value={additionalContext}
                      onChange={(e) => setAdditionalContext(e.target.value)}
                      placeholder="Mention we need their W-2 by March 15"
                      rows={3}
                      className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <button
                    onClick={handleGenerateDraft}
                    disabled={!purpose.trim() || drafting}
                    className="inline-flex items-center gap-2 rounded-md bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {drafting ? (
                      <>
                        <SmallSpinner />
                        Drafting email...
                      </>
                    ) : (
                      <>
                        <SparklesIcon />
                        Generate Draft
                      </>
                    )}
                  </button>
                  {draftError && (
                    <p className="text-sm text-red-600">{draftError}</p>
                  )}
                </div>
              )}
            </>
          ) : (
            /* Step 3: Review & edit */
            <div className="space-y-4">
              {approach !== "scratch" && (
                <button
                  onClick={() => {
                    setShowEditor(false);
                    setSubject("");
                    setBodyHtml("");
                    setAiDrafted(false);
                    setTemplateId(null);
                  }}
                  className="text-xs text-blue-600 hover:underline"
                >
                  &larr; Back
                </button>
              )}

              {aiDrafted && (
                <div className="inline-flex items-center gap-1.5 rounded-full bg-purple-50 px-2.5 py-1 text-[11px] font-medium text-purple-700">
                  <SparklesIcon />
                  AI-drafted
                </div>
              )}

              {/* To field */}
              <div>
                <label className="block text-xs font-medium text-gray-500">To</label>
                <input
                  type="email"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Subject */}
              <div>
                <label className="block text-xs font-medium text-gray-500">Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Email subject"
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Body */}
              <div>
                <label className="block text-xs font-medium text-gray-500">Body</label>
                <div
                  contentEditable
                  suppressContentEditableWarning
                  onBlur={(e) => setBodyHtml(e.currentTarget.innerHTML)}
                  dangerouslySetInnerHTML={{ __html: bodyHtml }}
                  className="mt-1 min-h-[200px] w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500 prose prose-sm max-w-none"
                />
              </div>

              {/* Follow-up reminder */}
              <div>
                <label className="block text-xs font-medium text-gray-500">Follow-up reminder</label>
                <select
                  value={followUpDays}
                  onChange={(e) => setFollowUpDays(Number(e.target.value))}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                >
                  {FOLLOW_UP_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        {/* Footer with send button */}
        {showEditor && (
          <div className="border-t border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <button
                onClick={onClose}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={sending || !to.trim() || !subject.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {sending ? (
                  <>
                    <SmallSpinner />
                    Sending...
                  </>
                ) : (
                  <>
                    <SendIcon />
                    Send Email
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Toast */}
        {toast && (
          <div
            className={`absolute bottom-20 left-1/2 -translate-x-1/2 rounded-lg px-4 py-2 text-xs font-medium shadow-lg ${
              toast.type === "success"
                ? "bg-green-700 text-white"
                : "bg-red-700 text-white"
            }`}
          >
            {toast.message}
          </div>
        )}
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes slide-in-right {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.2s ease-out;
        }
      `}} />
    </>
  );
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function TemplateIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

function SparklesIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
    </svg>
  );
}

function PenIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
    </svg>
  );
}

function SmallSpinner() {
  return (
    <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}
