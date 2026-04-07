"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import {
  ClientCommunication,
  CommunicationSendResponse,
  DraftEmailResponse,
  EmailTemplate,
  QuarterlyEstimateDraftResponse,
  RenderedTemplate,
  createCommunicationsApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type Approach = "template" | "ai" | "scratch" | "quarterly" | null;

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

  // Quarterly estimate state
  const [qeTaxYear, setQeTaxYear] = useState(new Date().getFullYear());
  const [qeQuarter, setQeQuarter] = useState(() => {
    const m = new Date().getMonth();
    if (m < 3) return 1;
    if (m < 5) return 2;
    if (m < 8) return 3;
    return 4;
  });
  const [qeDrafting, setQeDrafting] = useState(false);
  const [qeError, setQeError] = useState<string | null>(null);
  const [qeResult, setQeResult] = useState<QuarterlyEstimateDraftResponse | null>(null);
  const [qeOpenItemsExpanded, setQeOpenItemsExpanded] = useState(false);

  // Thread view state
  const [threadViewOpen, setThreadViewOpen] = useState(false);
  const [threadComms, setThreadComms] = useState<ClientCommunication[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);

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
    // "quarterly" and "ai" just show their form — no extra loading needed
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

  // ── Handle quarterly estimate draft ───────────────────────────────────────

  async function handleGenerateQuarterlyDraft() {
    setQeDrafting(true);
    setQeError(null);
    try {
      const result = await createCommunicationsApi(getToken).draftQuarterlyEstimate(clientId, qeTaxYear, qeQuarter);
      setQeResult(result);
      setSubject(result.subject);
      setBodyHtml(result.body_html);
      setFollowUpDays(7);
      setShowEditor(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to generate quarterly estimate draft.";
      setQeError(msg);
      showToast(msg, "error");
    } finally {
      setQeDrafting(false);
    }
  }

  // ── Load thread history ──────────────────────────────────────────────────

  async function loadThreadHistory(threadId: string) {
    setThreadLoading(true);
    try {
      const comms = await createCommunicationsApi(getToken).getThreadHistory(clientId, threadId);
      setThreadComms(comms);
      setThreadViewOpen(true);
    } catch {
      showToast("Failed to load thread history", "error");
    } finally {
      setThreadLoading(false);
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
        metadata: aiDrafted
          ? { ai_drafted: true, purpose }
          : qeResult
            ? { ai_drafted: true, quarterly_estimate: true }
            : undefined,
        ...(qeResult ? {
          thread_id: qeResult.thread_id,
          thread_type: qeResult.thread_type,
          thread_year: qeResult.thread_year,
          thread_quarter: qeResult.thread_quarter,
        } : {}),
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
                  <button
                    onClick={() => selectApproach("quarterly")}
                    className="group w-full rounded-xl border border-gray-200 p-4 text-left transition hover:border-emerald-300 hover:bg-emerald-50/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 group-hover:bg-emerald-100">
                        <CalculatorIcon />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">Quarterly Estimate</p>
                        <p className="text-xs text-gray-500">AI-drafted estimate email with financial context and thread history</p>
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

              {/* Quarterly estimate form */}
              {approach === "quarterly" && (
                <div className="space-y-4">
                  <button
                    onClick={() => setApproach(null)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    &larr; Back
                  </button>
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <CalculatorIcon />
                      <p className="text-sm font-semibold text-gray-900">Quarterly Estimated Tax Payment</p>
                    </div>
                    <p className="text-xs text-gray-500 mb-4">
                      Generate an AI-drafted email using {clientName}&apos;s financial data, prior correspondence, and open items.
                    </p>
                    <div className="flex items-end gap-3">
                      <div className="flex-1">
                        <label className="block text-xs font-medium text-gray-600 mb-1">Tax Year</label>
                        <select
                          value={qeTaxYear}
                          onChange={(e) => setQeTaxYear(Number(e.target.value))}
                          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                        >
                          {[0, 1, -1].map((offset) => {
                            const y = new Date().getFullYear() + offset;
                            return <option key={y} value={y}>{y}</option>;
                          })}
                        </select>
                      </div>
                      <div className="flex-1">
                        <label className="block text-xs font-medium text-gray-600 mb-1">Quarter</label>
                        <select
                          value={qeQuarter}
                          onChange={(e) => setQeQuarter(Number(e.target.value))}
                          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                        >
                          <option value={1}>Q1 — Due Apr 15</option>
                          <option value={2}>Q2 — Due Jun 15</option>
                          <option value={3}>Q3 — Due Sep 15</option>
                          <option value={4}>Q4 — Due Jan 15</option>
                        </select>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleGenerateQuarterlyDraft}
                    disabled={qeDrafting}
                    className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {qeDrafting ? (
                      <>
                        <SmallSpinner />
                        Analyzing financial data and prior correspondence...
                      </>
                    ) : (
                      <>
                        <SparklesIcon />
                        Generate Draft
                      </>
                    )}
                  </button>
                  {qeError && (
                    <p className="text-sm text-red-600">{qeError}</p>
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
                    setQeResult(null);
                    setQeOpenItemsExpanded(false);
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

              {/* Quarterly estimate context bar */}
              {qeResult && (
                <div className="space-y-2">
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CalculatorIcon />
                        <span className="text-xs font-semibold text-blue-800">
                          Q{qeResult.thread_quarter} {qeResult.thread_year} Estimated Tax Payment
                        </span>
                      </div>
                      <button
                        onClick={() => loadThreadHistory(qeResult.thread_id)}
                        disabled={threadLoading}
                        className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                      >
                        {threadLoading ? "Loading..." : "View Thread"}
                      </button>
                    </div>
                    {qeResult.financial_context_used.length > 0 && (
                      <p className="mt-1 text-[11px] text-blue-600">
                        Using {qeResult.financial_context_used.length} financial data points
                      </p>
                    )}
                  </div>

                  {/* Open items from prior correspondence */}
                  {qeResult.open_items_from_prior.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <button
                        onClick={() => setQeOpenItemsExpanded(!qeOpenItemsExpanded)}
                        className="flex w-full items-center justify-between text-left"
                      >
                        <span className="text-xs font-semibold text-amber-800">
                          {qeResult.open_items_from_prior.length} open item{qeResult.open_items_from_prior.length !== 1 ? "s" : ""} from prior emails
                        </span>
                        <svg
                          className={`h-4 w-4 text-amber-600 transition-transform ${qeOpenItemsExpanded ? "rotate-180" : ""}`}
                          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                      {qeOpenItemsExpanded && (
                        <ul className="mt-2 space-y-1.5">
                          {qeResult.open_items_from_prior.map((item, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-amber-700">
                              <span className="mt-0.5 block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400" />
                              {item.question}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
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

      {/* Thread view slide-over */}
      {threadViewOpen && (
        <>
          <div className="fixed inset-0 z-[60] bg-black/20" onClick={() => setThreadViewOpen(false)} />
          <div className="fixed inset-y-0 right-0 z-[70] flex w-full max-w-md flex-col bg-white shadow-2xl animate-slide-in-right">
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
              <h3 className="text-sm font-semibold text-gray-900">Thread History</h3>
              <button
                onClick={() => setThreadViewOpen(false)}
                className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {threadComms.length === 0 ? (
                <p className="text-sm text-gray-400">No prior emails in this thread.</p>
              ) : (
                <div className="space-y-4">
                  {threadComms.map((comm) => (
                    <div key={comm.id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-xs font-semibold text-gray-900 truncate flex-1">
                          {comm.subject}
                        </p>
                        <span className="ml-2 text-[10px] text-gray-400 whitespace-nowrap">
                          {new Date(comm.sent_at).toLocaleDateString()}
                        </span>
                      </div>
                      {comm.body_text && (
                        <p className="text-xs text-gray-500 line-clamp-3">
                          {comm.body_text.slice(0, 200)}
                        </p>
                      )}
                      {/* Show open items on this email */}
                      {comm.open_items && (comm.open_items as Array<{question: string; status: string}>).length > 0 && (
                        <div className="mt-2 border-t border-gray-100 pt-2">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-600 mb-1">
                            Open Items
                          </p>
                          {(comm.open_items as Array<{question: string; status: string}>).map((item, i) => (
                            <p key={i} className="text-[11px] text-amber-700 flex items-start gap-1.5">
                              <span className="mt-1 block h-1 w-1 flex-shrink-0 rounded-full bg-amber-400" />
                              {item.question}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}

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

function CalculatorIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 15.75V18m-7.5-6.75h.008v.008H8.25v-.008zm0 2.25h.008v.008H8.25v-.008zm0 2.25h.008v.008H8.25v-.008zm0 2.25h.008v.008H8.25v-.008zm2.498-6.75h.007v.008h-.007v-.008zm0 2.25h.007v.008h-.007v-.008zm0 2.25h.007v.008h-.007v-.008zm0 2.25h.007v.008h-.007v-.008zm2.504-6.75h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008v-.008zm1.498 2.25h.008v.008h-.008v-.008zm-1.498-6.75h.008v.008h-.008V18zM15.75 15.75h.008v.008h-.008v-.008zm0 2.25h.007v.008h-.007v-.008zM15 9.75a.75.75 0 00-.75.75v.008c0 .414.336.75.75.75h.008a.75.75 0 00.75-.75V10.5a.75.75 0 00-.75-.75H15zM4.5 19.5h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15A2.25 2.25 0 002.25 6.75v10.5A2.25 2.25 0 004.5 19.5zm6-10.125a1.875 1.875 0 11-3.75 0 1.875 1.875 0 013.75 0zm1.5-4.875h4.125a1.125 1.125 0 010 2.25H12a1.125 1.125 0 010-2.25z" />
    </svg>
  );
}

function SmallSpinner() {
  return (
    <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}
