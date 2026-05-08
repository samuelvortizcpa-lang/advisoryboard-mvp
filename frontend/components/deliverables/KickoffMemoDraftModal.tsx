"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { DeliverableDraftResponse, ReferencesPayload } from "@/lib/api";
import { createDeliverablesApi } from "@/lib/api";
import ClientFacingTasksList from "./ClientFacingTasksList";
import StrategiesReferencedList from "./StrategiesReferencedList";

interface KickoffMemoDraftModalProps {
  open: boolean;
  onClose: () => void;
  clientId: string;
  clientName: string;
  clientEmail: string | null;
}

export default function KickoffMemoDraftModal({
  open,
  onClose,
  clientId,
  clientName,
  clientEmail,
}: KickoffMemoDraftModalProps) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [references, setReferences] = useState<ReferencesPayload | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [recipientEmail, setRecipientEmail] = useState(clientEmail ?? "");
  const [taxYear, setTaxYear] = useState(new Date().getFullYear());
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const api = useCallback(
    () => createDeliverablesApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  const fetchDraft = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res: DeliverableDraftResponse = await api().draftKickoffMemo(clientId, taxYear);
      setSubject(res.subject);
      setBody(res.body);
      setReferences(res.references);
      setWarnings(res.warnings);
    } catch {
      setError("Failed to generate draft. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [api, clientId, taxYear]);

  // Fetch draft when modal opens
  useEffect(() => {
    if (open) {
      fetchDraft();
    }
  }, [open, fetchDraft]);

  const handleSend = async () => {
    setSending(true);
    setToast(null);
    try {
      await api().sendKickoffMemo(clientId, {
        tax_year: taxYear,
        subject,
        body,
        recipient_email: recipientEmail,
      });
      setToast({ message: "Kickoff memo sent successfully", type: "success" });
      setTimeout(() => onClose(), 1200);
    } catch {
      setToast({ message: "Failed to send. Please try again.", type: "error" });
    } finally {
      setSending(false);
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-white shadow-2xl animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Draft Kickoff Memo</h2>
            <p className="text-xs text-gray-500">{clientName} — {taxYear}</p>
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

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Loading state */}
          {loading && (
            <div className="flex items-center gap-2 py-8 justify-center text-sm text-gray-500">
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Generating draft...
            </div>
          )}

          {/* Error state */}
          {!loading && error && (
            <div className="py-8 text-center">
              <p className="text-sm text-red-600 mb-3">{error}</p>
              <button
                onClick={fetchDraft}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Retry
              </button>
            </div>
          )}

          {/* Editable state */}
          {!loading && !error && (
            <>
              {/* Warnings banner */}
              {warnings.length > 0 && (
                <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2">
                  {warnings.map((w, i) => (
                    <p key={i} className="text-xs text-amber-700">{w}</p>
                  ))}
                </div>
              )}

              {/* Tax year */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Tax Year</label>
                <input
                  type="number"
                  value={taxYear}
                  onChange={(e) => setTaxYear(Number(e.target.value))}
                  className="w-24 rounded-md border border-gray-300 px-2 py-1 text-sm"
                />
              </div>

              {/* Recipient email */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Recipient Email</label>
                <input
                  type="email"
                  required
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="client@example.com"
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                />
              </div>

              {/* Subject */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                />
              </div>

              {/* Body */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Body</label>
                <textarea
                  rows={20}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono leading-relaxed"
                />
              </div>

              {/* References */}
              {references && (
                <div className="space-y-3 border-t border-gray-100 pt-3">
                  <StrategiesReferencedList strategies={references.strategies} />
                  <ClientFacingTasksList tasks={references.tasks} />
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!loading && !error && (
          <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-3">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSend}
              disabled={sending || !recipientEmail}
              className="inline-flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sending ? "Sending…" : "Send via Gmail"}
            </button>
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
    </>
  );
}
