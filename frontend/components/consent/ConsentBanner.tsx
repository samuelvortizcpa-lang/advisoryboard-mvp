"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ConsentCreateRequest,
  ConsentRecord,
  ConsentStatus,
  createConsentApi,
} from "@/lib/api";
import HelpTooltip from "@/components/ui/HelpTooltip";

// ─── Types ──────────────────────────────────────────────────────────────────

interface Props {
  clientId: string;
  clientName: string;
  clientEmail?: string | null;
  getToken: () => Promise<string | null>;
  userName?: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function oneYearFromISO(dateStr: string): string {
  const d = new Date(dateStr);
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
}

function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const diff = Date.now() - new Date(iso).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function ConsentBanner({
  clientId,
  clientName,
  clientEmail,
  getToken,
  userName,
}: Props) {
  const [status, setStatus] = useState<ConsentStatus | null>(null);
  const [history, setHistory] = useState<ConsentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [settingPreparer, setSettingPreparer] = useState(false);
  const [acknowledging, setAcknowledging] = useState(false);
  const [showLearnMore, setShowLearnMore] = useState(false);
  const [showAckDetails, setShowAckDetails] = useState(false);

  // Send-for-signature state
  const [showSendForm, setShowSendForm] = useState(false);
  const [sendEmail, setSendEmail] = useState(clientEmail ?? "");
  const [sendTaxpayerName, setSendTaxpayerName] = useState(clientName);
  const [sendPreparerName, setSendPreparerName] = useState(userName ?? "");
  const [sendPreparerFirm, setSendPreparerFirm] = useState("");
  const [sending, setSending] = useState(false);

  // Record-consent form state
  const [consentType, setConsentType] = useState("both");
  const [consentMethod, setConsentMethod] = useState("paper");
  const [consentDate, setConsentDate] = useState(todayISO());
  const [expirationDate, setExpirationDate] = useState(
    oneYearFromISO(todayISO())
  );
  const [taxpayerName, setTaxpayerName] = useState(clientName);
  const [preparerName, setPreparerName] = useState(userName ?? "");
  const [preparerFirm, setPreparerFirm] = useState("");
  const [engagementRef, setEngagementRef] = useState("");
  const [notes, setNotes] = useState("");

  const isEngagementLetter = consentMethod === "existing_engagement";

  const api = createConsentApi(getToken);

  const refresh = useCallback(async () => {
    try {
      const s = await api.getStatus(clientId);
      setStatus(s);
    } catch {
      /* non-fatal */
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  // Update expiration when consent date changes
  useEffect(() => {
    if (consentDate) {
      setExpirationDate(oneYearFromISO(consentDate));
    }
  }, [consentDate]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  async function handleSaveConsent() {
    setSaving(true);
    try {
      const data: ConsentCreateRequest = {
        consent_type: consentType,
        status: "obtained",
        consent_date: new Date(consentDate).toISOString(),
        expiration_date: new Date(expirationDate).toISOString(),
        consent_method: consentMethod,
        taxpayer_name: isEngagementLetter ? null : taxpayerName || null,
        preparer_name: preparerName || null,
        preparer_firm: preparerFirm || null,
        notes: buildNotes(),
      };
      await api.create(clientId, data);
      setShowForm(false);
      setToast("Consent record saved successfully");
      await refresh();
    } catch (err) {
      setToast(
        err instanceof Error ? err.message : "Failed to save consent record"
      );
    } finally {
      setSaving(false);
    }
  }

  function buildNotes(): string {
    if (isEngagementLetter) {
      let base =
        "Consent covered by existing engagement letter. CPA has confirmed that the engagement terms authorize disclosure to third-party document management platforms.";
      if (engagementRef) base += ` Reference: ${engagementRef}`;
      if (notes) base += `\n${notes}`;
      return base;
    }
    return notes;
  }

  async function handleGenerateForm() {
    setGenerating(true);
    try {
      await api.downloadForm(clientId);
      setToast("Consent form downloaded \u2014 have your client sign and return it");
    } catch (err) {
      setToast(
        err instanceof Error ? err.message : "Failed to generate consent form"
      );
    } finally {
      setGenerating(false);
    }
  }

  async function handleSendForSignature() {
    if (!isValidEmail(sendEmail)) {
      setToast("Please enter a valid email address");
      return;
    }
    setSending(true);
    try {
      await api.sendForSignature(clientId, {
        taxpayer_email: sendEmail,
        taxpayer_name: sendTaxpayerName,
        preparer_name: sendPreparerName,
        preparer_firm: sendPreparerFirm || undefined,
      });
      setShowSendForm(false);
      setToast(`Consent form sent to ${sendEmail} \u2014 you\u2019ll be notified when they sign`);
      await refresh();
    } catch (err) {
      setToast(
        err instanceof Error ? err.message : "Failed to send consent form"
      );
    } finally {
      setSending(false);
    }
  }

  async function handleShowHistory() {
    if (showHistory) {
      setShowHistory(false);
      return;
    }
    try {
      const h = await api.history(clientId);
      setHistory(h);
      setShowHistory(true);
    } catch {
      /* non-fatal */
    }
  }

  function openFormWithEngagement() {
    setConsentMethod("existing_engagement");
    setNotes("");
    setShowForm(true);
    setShowSendForm(false);
  }

  function openRecordManually() {
    setConsentMethod("paper");
    setShowForm(true);
    setShowSendForm(false);
  }

  function openSendForm() {
    setSendEmail(clientEmail ?? "");
    setSendTaxpayerName(clientName);
    setSendPreparerName(userName ?? "");
    setSendPreparerFirm("");
    setShowSendForm(true);
    setShowForm(false);
  }

  async function handleSetPreparerStatus(isPreparer: boolean) {
    setSettingPreparer(true);
    try {
      const updated = await api.setPreparerStatus(clientId, isPreparer);
      setStatus(updated);
      setToast(
        isPreparer
          ? "Preparer relationship confirmed — 7216 consent is required"
          : "Advisory relationship confirmed"
      );
    } catch (err) {
      setToast(
        err instanceof Error ? err.message : "Failed to update preparer status"
      );
    } finally {
      setSettingPreparer(false);
    }
  }

  async function handleAdvisoryAcknowledgment() {
    setAcknowledging(true);
    try {
      await api.recordAdvisoryAcknowledgment(clientId);
      setToast("AICPA acknowledgment recorded");
      await refresh();
    } catch (err) {
      setToast(
        err instanceof Error ? err.message : "Failed to record acknowledgment"
      );
    } finally {
      setAcknowledging(false);
    }
  }

  // ── Don't render if not applicable ──────────────────────────────────────────

  if (loading || !status) return null;

  const { consent_status, has_tax_documents, latest_consent, is_expired, days_until_expiry } = status;

  // Nothing to show if no tax documents
  if (!has_tax_documents && consent_status === "not_required") return null;

  // ── Status-specific rendering ───────────────────────────────────────────────

  const effectiveStatus = is_expired ? "expired" : consent_status;

  return (
    <div className="px-8 pt-4">
      {/* ── Toast ──────────────────────────────────────────────────────────── */}
      {toast && (
        <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm text-blue-700">
          {toast}
        </div>
      )}

      {/* ── Determination needed — preparer status unknown ────────────────── */}
      {effectiveStatus === "determination_needed" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-start gap-3">
            <HelpCircleIcon className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
            <div className="flex-1">
              <p className="flex items-center gap-1 text-sm font-semibold text-blue-800">
                Tax Documents Detected
                <HelpTooltip content="IRC Section 7216 requires written consent before sharing tax return information with AI systems. Green means consent is obtained." position="right" maxWidth={260} />
              </p>
              <p className="mt-1 text-sm text-blue-700">
                You&apos;ve uploaded tax return documents for this client. To
                determine the appropriate data handling requirements, please
                confirm your relationship:
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  onClick={() => handleSetPreparerStatus(true)}
                  disabled={settingPreparer}
                  className="inline-flex items-center gap-1.5 rounded-md border border-blue-300 bg-white px-3.5 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-50 disabled:opacity-50"
                >
                  <ShieldWarningIcon className="h-4 w-4" />
                  I Prepare This Client&apos;s Returns
                </button>
                <button
                  onClick={() => handleSetPreparerStatus(false)}
                  disabled={settingPreparer}
                  className="inline-flex items-center gap-1.5 rounded-md border border-blue-300 bg-white px-3.5 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-50 disabled:opacity-50"
                >
                  <BriefcaseIcon className="h-4 w-4" />
                  Advisory / Consulting Only
                </button>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-blue-600">
                This determines whether IRC Section 7216 consent is required.
                7216 applies only when you are the tax return preparer. Advisory
                engagements using prior returns prepared by another firm are
                subject to AICPA confidentiality standards instead.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Advisory acknowledgment needed ──────────────────────────────── */}
      {effectiveStatus === "advisory_acknowledgment_needed" && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 p-4">
          <div className="flex items-start gap-3">
            <ShieldCheckIcon className="mt-0.5 h-5 w-5 shrink-0 text-teal-600" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-teal-800">
                Data Handling Acknowledgment
              </p>
              <p className="mt-1 text-sm text-teal-700">
                As an advisory engagement, this client&apos;s tax documents are
                covered by AICPA Confidential Client Information standards
                (Section 1.700.001) rather than IRC Section 7216. Please confirm
                that your engagement letter authorizes the use of third-party
                document platforms.
              </p>
              <div className="mt-3">
                <button
                  onClick={handleAdvisoryAcknowledgment}
                  disabled={acknowledging}
                  className="inline-flex items-center gap-1.5 rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700 disabled:opacity-50"
                >
                  {acknowledging
                    ? "Confirming..."
                    : "I Confirm \u2014 Engagement Letter Covers This"}
                </button>
              </div>
              <div className="mt-3">
                <button
                  onClick={() => setShowLearnMore(!showLearnMore)}
                  className="text-xs font-medium text-teal-600 underline decoration-teal-300 hover:text-teal-800"
                >
                  {showLearnMore ? "Show less" : "Learn more"}
                </button>
                {showLearnMore && (
                  <p className="mt-2 text-xs leading-relaxed text-teal-600">
                    Section 7216 applies specifically to tax return preparers
                    handling information furnished in connection with return
                    preparation. Since you indicated this is an advisory-only
                    engagement, the tax documents uploaded here are treated as
                    confidential client information under AICPA standards rather
                    than 7216 &ldquo;tax return information.&rdquo; Your standard
                    engagement letter and our platform&apos;s encryption, access
                    controls, and data isolation policies provide the appropriate
                    level of protection. If your relationship with this client
                    changes to include tax preparation, you can update this
                    designation from the client settings.
                  </p>
                )}
              </div>
              <button
                onClick={() => handleSetPreparerStatus(true)}
                disabled={settingPreparer}
                className="mt-2 text-xs text-teal-600 underline decoration-teal-300 hover:text-teal-800 disabled:opacity-50"
              >
                Actually, I do prepare this client&apos;s returns &rarr;
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Acknowledged — advisory AICPA complete ──────────────────────── */}
      {effectiveStatus === "acknowledged" && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-2.5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <ShieldCheckIcon className="h-4 w-4 text-green-600" />
              <p className="text-sm text-green-700">
                <span className="font-medium">Data Handling:</span> Acknowledged
                on {fmtDate(status.latest_consent?.consent_date)} &mdash;
                Advisory engagement, AICPA standards apply
              </p>
            </div>
            <button
              onClick={() => setShowAckDetails(!showAckDetails)}
              className="text-xs font-medium text-green-600 hover:text-green-800"
            >
              {showAckDetails ? "Hide" : "View Details"}
            </button>
          </div>
          {showAckDetails && status.latest_consent && (
            <div className="mt-2.5 border-t border-green-200 pt-2.5">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
                <div>
                  <dt className="text-green-600">Acknowledged</dt>
                  <dd className="font-medium text-green-800">
                    {fmtDate(status.latest_consent.consent_date)}
                  </dd>
                </div>
                <div>
                  <dt className="text-green-600">Tier</dt>
                  <dd className="font-medium text-green-800">
                    AICPA Acknowledgment
                  </dd>
                </div>
                {status.latest_consent.notes && (
                  <div className="col-span-full">
                    <dt className="text-green-600">Notes</dt>
                    <dd className="font-medium text-green-800">
                      {status.latest_consent.notes}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          )}
        </div>
      )}

      {/* ── Pending consent ────────────────────────────────────────────────── */}
      {effectiveStatus === "pending" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-start gap-3">
            <ShieldWarningIcon className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-amber-800">
                Section 7216 Consent Required
              </p>
              <p className="mt-1 text-sm text-amber-700">
                Tax documents have been uploaded for this client. Federal law
                requires written taxpayer consent before their tax return
                information can be used for AI analysis.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  onClick={openSendForm}
                  className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-amber-700"
                >
                  <MailIcon className="h-3.5 w-3.5" />
                  Send for Signature
                </button>
                <button
                  onClick={handleGenerateForm}
                  disabled={generating}
                  className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50"
                >
                  {generating ? "Generating..." : "Generate PDF"}
                </button>
                <button
                  onClick={openRecordManually}
                  className="text-xs font-medium text-amber-600 underline decoration-amber-300 hover:text-amber-800"
                >
                  Record Manually
                </button>
              </div>
              <button
                onClick={openFormWithEngagement}
                className="mt-2 text-xs text-amber-600 underline decoration-amber-300 hover:text-amber-800"
              >
                Already covered by an existing engagement letter?
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Sent — awaiting signature ──────────────────────────────────────── */}
      {effectiveStatus === "sent" && latest_consent && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-start gap-3">
            <MailIcon className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-blue-800">
                Consent Form Sent &mdash; Awaiting Signature
              </p>
              <p className="mt-1 text-sm text-blue-700">
                Sent to{" "}
                <span className="font-medium">
                  {latest_consent.sent_to_email}
                </span>{" "}
                on {fmtDate(latest_consent.sent_at)}
              </p>
              {(() => {
                const days = daysSince(latest_consent.sent_at);
                if (days != null && days >= 7) {
                  return (
                    <p className="mt-1.5 text-xs font-medium text-amber-700">
                      It&apos;s been {days} days since this was sent. You may
                      want to follow up.
                    </p>
                  );
                }
                return null;
              })()}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  onClick={openSendForm}
                  className="inline-flex items-center gap-1.5 rounded-md border border-blue-300 bg-white px-3 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50"
                >
                  Resend
                </button>
                <button
                  onClick={openRecordManually}
                  className="text-xs font-medium text-blue-600 underline decoration-blue-300 hover:text-blue-800"
                >
                  Record Manually
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Obtained — electronic signature ────────────────────────────────── */}
      {effectiveStatus === "obtained" &&
        latest_consent?.consent_method === "electronic" && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ShieldCheckIcon className="h-4 w-4 text-green-600" />
                <p className="text-sm text-green-700">
                  <span className="font-medium">7216 Consent: </span>
                  Signed electronically by{" "}
                  <span className="font-medium">
                    {latest_consent.signer_typed_name ??
                      latest_consent.taxpayer_name ??
                      "client"}
                  </span>{" "}
                  on {fmtDate(latest_consent.signed_at ?? latest_consent.consent_date)}
                  {latest_consent.expiration_date && (
                    <>
                      {" "}&mdash; Expires {fmtDate(latest_consent.expiration_date)}
                      {days_until_expiry != null && (
                        <span className="text-green-600">
                          {" "}({days_until_expiry} days)
                        </span>
                      )}
                    </>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {latest_consent.signed_pdf_url && (
                  <a
                    href={latest_consent.signed_pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-medium text-green-600 hover:text-green-800"
                  >
                    Download Signed PDF
                  </a>
                )}
                <button
                  onClick={() => setShowDetails(!showDetails)}
                  className="text-xs font-medium text-green-600 hover:text-green-800"
                >
                  {showDetails ? "Hide" : "Details"}
                </button>
              </div>
            </div>

            {showDetails && (
              <div className="mt-3 border-t border-green-200 pt-3">
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="text-green-600">Type</dt>
                    <dd className="font-medium text-green-800">
                      {consentTypeLabel(latest_consent.consent_type)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Method</dt>
                    <dd className="font-medium text-green-800">
                      Electronic signature
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Signed by</dt>
                    <dd className="font-medium text-green-800">
                      {latest_consent.signer_typed_name ?? "\u2014"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Sent to</dt>
                    <dd className="font-medium text-green-800">
                      {latest_consent.sent_to_email ?? "\u2014"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Preparer</dt>
                    <dd className="font-medium text-green-800">
                      {latest_consent.preparer_name ?? "\u2014"}
                    </dd>
                  </div>
                  {latest_consent.preparer_firm && (
                    <div>
                      <dt className="text-green-600">Firm</dt>
                      <dd className="font-medium text-green-800">
                        {latest_consent.preparer_firm}
                      </dd>
                    </div>
                  )}
                </dl>
              </div>
            )}
          </div>
        )}

      {/* ── Obtained — engagement letter ───────────────────────────────────── */}
      {effectiveStatus === "obtained" &&
        latest_consent?.consent_method === "existing_engagement" && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ShieldCheckIcon className="h-4 w-4 text-green-600" />
                <p className="text-sm text-green-700">
                  <span className="font-medium">7216 Consent: </span>
                  Covered by existing engagement letter &mdash; recorded{" "}
                  {fmtDate(latest_consent.consent_date)}
                  {latest_consent.expiration_date && (
                    <>
                      {" "}&mdash; Expires {fmtDate(latest_consent.expiration_date)}
                      {days_until_expiry != null && (
                        <span className="text-green-600">
                          {" "}({days_until_expiry} days)
                        </span>
                      )}
                    </>
                  )}
                </p>
              </div>
              <button
                onClick={() => setShowDetails(!showDetails)}
                className="text-xs font-medium text-green-600 hover:text-green-800"
              >
                {showDetails ? "Hide" : "Details"}
              </button>
            </div>

            {showDetails && (
              <div className="mt-3 border-t border-green-200 pt-3">
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="text-green-600">Type</dt>
                    <dd className="font-medium text-green-800">
                      {consentTypeLabel(latest_consent.consent_type)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Method</dt>
                    <dd className="font-medium text-green-800">
                      Engagement letter
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Preparer</dt>
                    <dd className="font-medium text-green-800">
                      {latest_consent.preparer_name ?? "\u2014"}
                    </dd>
                  </div>
                  {latest_consent.preparer_firm && (
                    <div>
                      <dt className="text-green-600">Firm</dt>
                      <dd className="font-medium text-green-800">
                        {latest_consent.preparer_firm}
                      </dd>
                    </div>
                  )}
                  {latest_consent.notes && (
                    <div className="col-span-full">
                      <dt className="text-green-600">Notes</dt>
                      <dd className="font-medium text-green-800">
                        {latest_consent.notes}
                      </dd>
                    </div>
                  )}
                </dl>
              </div>
            )}
          </div>
        )}

      {/* ── Obtained — other methods (paper, verbal, etc.) ─────────────────── */}
      {effectiveStatus === "obtained" &&
        latest_consent?.consent_method !== "electronic" &&
        latest_consent?.consent_method !== "existing_engagement" && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ShieldCheckIcon className="h-4 w-4 text-green-600" />
                <p className="text-sm text-green-700">
                  <span className="font-medium">7216 Consent: </span>
                  Obtained on {fmtDate(latest_consent?.consent_date)}
                  {latest_consent?.expiration_date && (
                    <>
                      {" "}&mdash; Expires {fmtDate(latest_consent.expiration_date)}
                      {days_until_expiry != null && (
                        <span className="text-green-600">
                          {" "}({days_until_expiry} days)
                        </span>
                      )}
                    </>
                  )}
                </p>
              </div>
              <button
                onClick={() => setShowDetails(!showDetails)}
                className="text-xs font-medium text-green-600 hover:text-green-800"
              >
                {showDetails ? "Hide" : "View Details"}
              </button>
            </div>

            {showDetails && latest_consent && (
              <div className="mt-3 border-t border-green-200 pt-3">
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="text-green-600">Type</dt>
                    <dd className="font-medium text-green-800">
                      {consentTypeLabel(latest_consent.consent_type)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Method</dt>
                    <dd className="font-medium text-green-800">
                      {methodLabel(latest_consent.consent_method)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Taxpayer</dt>
                    <dd className="font-medium text-green-800">
                      {latest_consent.taxpayer_name ?? "\u2014"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-green-600">Preparer</dt>
                    <dd className="font-medium text-green-800">
                      {latest_consent.preparer_name ?? "\u2014"}
                    </dd>
                  </div>
                  {latest_consent.preparer_firm && (
                    <div>
                      <dt className="text-green-600">Firm</dt>
                      <dd className="font-medium text-green-800">
                        {latest_consent.preparer_firm}
                      </dd>
                    </div>
                  )}
                  {latest_consent.notes && (
                    <div className="col-span-full">
                      <dt className="text-green-600">Notes</dt>
                      <dd className="font-medium text-green-800">
                        {latest_consent.notes}
                      </dd>
                    </div>
                  )}
                </dl>
              </div>
            )}
          </div>
        )}

      {/* ── Expired ────────────────────────────────────────────────────────── */}
      {effectiveStatus === "expired" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-start gap-3">
            <ShieldWarningIcon className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-red-800">
                Section 7216 Consent Expired
              </p>
              <p className="mt-1 text-sm text-red-700">
                Consent for this client expired on{" "}
                {fmtDate(latest_consent?.expiration_date)}. Please obtain
                renewed consent.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  onClick={openSendForm}
                  className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700"
                >
                  <MailIcon className="h-3.5 w-3.5" />
                  Send for Signature
                </button>
                <button
                  onClick={handleGenerateForm}
                  disabled={generating}
                  className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50"
                >
                  {generating ? "Generating..." : "Generate PDF"}
                </button>
                <button
                  onClick={openRecordManually}
                  className="text-xs font-medium text-red-600 underline decoration-red-300 hover:text-red-800"
                >
                  Record Manually
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Declined ───────────────────────────────────────────────────────── */}
      {effectiveStatus === "declined" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-start gap-3">
            <ShieldWarningIcon className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
            <div>
              <p className="text-sm font-semibold text-red-800">
                Section 7216 Consent Declined
              </p>
              <p className="mt-1 text-sm text-red-700">
                This client has declined consent. Tax return information should
                not be uploaded or analyzed for this client.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Send-for-signature inline form ──────────────────────────────────── */}
      {showSendForm && (
        <div className="mt-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900">
            Send Consent Form for Electronic Signature
          </h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Client Email
              </label>
              <input
                type="email"
                value={sendEmail}
                onChange={(e) => setSendEmail(e.target.value)}
                placeholder="client@example.com"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {sendEmail && !isValidEmail(sendEmail) && (
                <p className="mt-1 text-xs text-red-500">
                  Please enter a valid email address
                </p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Taxpayer Name
              </label>
              <input
                type="text"
                value={sendTaxpayerName}
                onChange={(e) => setSendTaxpayerName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Preparer Name
              </label>
              <input
                type="text"
                value={sendPreparerName}
                onChange={(e) => setSendPreparerName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Firm Name (optional)
              </label>
              <input
                type="text"
                value={sendPreparerFirm}
                onChange={(e) => setSendPreparerFirm(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleSendForSignature}
              disabled={sending || !isValidEmail(sendEmail) || !sendTaxpayerName.trim() || !sendPreparerName.trim()}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {sending ? "Sending..." : "Send Consent Form"}
            </button>
            <button
              onClick={() => setShowSendForm(false)}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Inline record consent form ─────────────────────────────────────── */}
      {showForm && (
        <div className="mt-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900">
            Record Consent
          </h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {/* Consent type */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Consent Type
              </label>
              <select
                value={consentType}
                onChange={(e) => setConsentType(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="both">Disclosure &amp; Use (recommended)</option>
                <option value="disclosure">Disclosure only</option>
                <option value="use">Use only</option>
              </select>
            </div>

            {/* Consent method */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Consent Method
              </label>
              <select
                value={consentMethod}
                onChange={(e) => setConsentMethod(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="paper">Paper form signed</option>
                <option value="electronic">Electronic signature</option>
                <option value="existing_engagement">
                  Covered by existing engagement letter
                </option>
                <option value="verbal_followup">
                  Verbal (follow-up written needed)
                </option>
              </select>
            </div>

            {/* Engagement letter helper */}
            {isEngagementLetter && (
              <div className="col-span-full rounded-md border border-blue-100 bg-blue-50 p-3">
                <p className="text-xs text-blue-700">
                  If your existing engagement letter or prior 7216 consent
                  covers disclosure to third-party document management
                  platforms, you can record that here. Enter the date of the
                  original engagement letter below.
                </p>
              </div>
            )}

            {/* Consent date */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                {isEngagementLetter ? "Engagement Letter Date" : "Consent Date"}
              </label>
              <input
                type="date"
                value={consentDate}
                onChange={(e) => setConsentDate(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Expiration date */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Expiration Date
              </label>
              <input
                type="date"
                value={expirationDate}
                onChange={(e) => setExpirationDate(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Taxpayer name (hidden for engagement letter) */}
            {!isEngagementLetter && (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Taxpayer Name
                </label>
                <input
                  type="text"
                  value={taxpayerName}
                  onChange={(e) => setTaxpayerName(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            )}

            {/* Preparer name */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Preparer Name
              </label>
              <input
                type="text"
                value={preparerName}
                onChange={(e) => setPreparerName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Preparer firm */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Preparer Firm (optional)
              </label>
              <input
                type="text"
                value={preparerFirm}
                onChange={(e) => setPreparerFirm(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Engagement letter reference */}
            {isEngagementLetter && (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Engagement Letter Reference (optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g., 2024 Tax Engagement Letter"
                  value={engagementRef}
                  onChange={(e) => setEngagementRef(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            )}

            {/* Notes */}
            <div className="col-span-full">
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Notes (optional)
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              onClick={handleSaveConsent}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Consent Record"}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Consent history toggle ────────────────────────────────────────── */}
      {has_tax_documents && (
        <div className="mt-2">
          <button
            onClick={handleShowHistory}
            className="text-xs font-medium text-gray-500 hover:text-gray-700"
          >
            {showHistory ? "Hide Consent History" : "Consent History"}
          </button>

          {showHistory && (
            <div className="mt-2 overflow-hidden rounded-lg border border-gray-200">
              <table className="min-w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Date
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Type
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Status
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Method
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Expires
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Notes
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {history.length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-3 py-4 text-center text-gray-400"
                      >
                        No consent records found
                      </td>
                    </tr>
                  )}
                  {history.map((r) => (
                    <tr key={r.id}>
                      <td className="px-3 py-2 text-gray-700">
                        {fmtDate(r.consent_date ?? r.created_at)}
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        {consentTypeLabel(r.consent_type)}
                      </td>
                      <td className="px-3 py-2">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        {methodLabel(r.consent_method)}
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        {fmtDate(r.expiration_date)}
                      </td>
                      <td className="max-w-[200px] truncate px-3 py-2 text-gray-500">
                        {r.notes ?? "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Helper label functions ───────────────────────────────────────────────────

function consentTypeLabel(t: string | null): string {
  if (!t) return "\u2014";
  if (t === "both") return "Disclosure & Use";
  if (t === "disclosure") return "Disclosure";
  if (t === "use") return "Use";
  return t;
}

function methodLabel(m: string | null): string {
  if (!m) return "\u2014";
  const map: Record<string, string> = {
    paper: "Paper form",
    electronic: "Electronic",
    existing_engagement: "Engagement letter",
    verbal_followup: "Verbal",
    platform_acknowledgment: "Platform acknowledgment",
  };
  return map[m] ?? m;
}

// ─── Status badge ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "obtained"
      ? "bg-green-100 text-green-700"
      : status === "pending"
      ? "bg-amber-100 text-amber-700"
      : status === "sent"
      ? "bg-blue-100 text-blue-700"
      : status === "expired" || status === "declined" || status === "revoked"
      ? "bg-red-100 text-red-700"
      : "bg-gray-100 text-gray-700";

  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function ShieldWarningIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function ShieldCheckIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  );
}

function MailIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function HelpCircleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function BriefcaseIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
      <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
    </svg>
  );
}
