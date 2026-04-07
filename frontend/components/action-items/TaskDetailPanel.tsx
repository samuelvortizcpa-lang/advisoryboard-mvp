"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";

import {
  ActionItem,
  ActionItemCreate,
  OrgMember,
  createActionItemsApi,
  createClientsApi,
  createOrganizationsApi,
  Client,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import SendEmailModal from "@/components/communications/SendEmailModal";

interface Props {
  item: ActionItem | null; // null = creating new
  isOpen: boolean;
  clientId?: string; // pre-filled for creation from client context
  defaultDueDate?: string; // pre-fill due_date for creation
  onClose: () => void;
  onSaved: (item: ActionItem) => void;
  onDeleted?: (id: string) => void;
}

export default function TaskDetailPanel({
  item,
  isOpen,
  clientId,
  defaultDueDate,
  onClose,
  onSaved,
  onDeleted,
}: Props) {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();

  // Form state
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"pending" | "completed">("pending");
  const [priority, setPriority] = useState<string>("");
  const [dueDate, setDueDate] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [assignedToName, setAssignedToName] = useState("");
  const [notes, setNotes] = useState("");
  const [selectedClientId, setSelectedClientId] = useState("");

  // UI state
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [showEstimateEmail, setShowEstimateEmail] = useState(false);
  const [estimateEmailSent, setEstimateEmailSent] = useState(false);
  const [estimateClient, setEstimateClient] = useState<Client | null>(null);

  // Animation state: mounted = in DOM, visible = slide-in triggered
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isCreating = !item;

  // Mount/unmount with animation
  useEffect(() => {
    if (isOpen) {
      setMounted(true);
      // Trigger slide-in on next frame so the initial translate-x-full is painted first
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setVisible(true);
        });
      });
    } else {
      // Slide out, then unmount after transition
      setVisible(false);
      const timer = setTimeout(() => setMounted(false), 200);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Initialize form from item
  useEffect(() => {
    if (!isOpen) return;
    if (item) {
      setText(item.text);
      setStatus(item.status === "completed" ? "completed" : "pending");
      setPriority(item.priority ?? "");
      setDueDate(item.due_date ?? "");
      setAssignedTo(item.assigned_to ?? "");
      setAssignedToName(item.assigned_to_name ?? "");
      setNotes(item.notes ?? "");
      setSelectedClientId(item.client_id);
    } else {
      setText("");
      setStatus("pending");
      setPriority("");
      setDueDate(defaultDueDate ?? "");
      setAssignedTo("");
      setAssignedToName("");
      setNotes("");
      setSelectedClientId(clientId ?? "");
    }
  }, [item, isOpen, clientId, defaultDueDate]);

  // Fetch org members
  useEffect(() => {
    if (!isOpen || !activeOrg?.id) return;
    createOrganizationsApi(getToken)
      .listMembers(activeOrg.id)
      .then(setMembers)
      .catch(() => {});
  }, [isOpen, activeOrg?.id, getToken]);

  // Fetch clients for creation without clientId context
  useEffect(() => {
    if (!isOpen || !isCreating || clientId) return;
    createClientsApi(getToken, activeOrg?.id)
      .list(0, 200)
      .then((r) => setClients(r.items))
      .catch(() => {});
  }, [isOpen, isCreating, clientId, activeOrg?.id, getToken]);

  // Escape key
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  // Auto-focus textarea for new items
  useEffect(() => {
    if (isOpen && isCreating && textareaRef.current) {
      setTimeout(() => textareaRef.current?.focus(), 200);
    }
  }, [isOpen, isCreating]);

  // Toast auto-clear
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  async function handleSave() {
    if (!text.trim()) return;
    setSaving(true);
    try {
      const api = createActionItemsApi(getToken, activeOrg?.id);
      if (isCreating) {
        const targetClientId = clientId || selectedClientId;
        if (!targetClientId) return;
        const data: ActionItemCreate = {
          text: text.trim(),
          client_id: targetClientId,
          ...(priority && { priority }),
          ...(dueDate && { due_date: dueDate }),
          ...(assignedTo && { assigned_to: assignedTo, assigned_to_name: assignedToName }),
          ...(notes.trim() && { notes: notes.trim() }),
        };
        const created = await api.create(data);
        setToast("Task created");
        onSaved(created);
        onClose();
      } else {
        const data: Record<string, unknown> = {
          text: text.trim(),
          status,
          priority: priority || null,
          due_date: dueDate || null,
          assigned_to: assignedTo || null,
          assigned_to_name: assignedToName || null,
          notes: notes.trim() || null,
        };
        const updated = await api.update(item.id, data);
        setToast("Changes saved");
        onSaved(updated);
      }
    } catch {
      setToast("Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!item) return;
    if (!window.confirm("Delete this action item? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await createActionItemsApi(getToken, activeOrg?.id).delete(item.id);
      onDeleted?.(item.id);
      onClose();
    } catch {
      setToast("Failed to delete");
    } finally {
      setDeleting(false);
    }
  }

  function handleAssignmentChange(userId: string) {
    setAssignedTo(userId);
    const member = members.find((m) => m.user_id === userId);
    setAssignedToName(member?.user_name ?? "");
  }

  if (!mounted) return null;

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${
          visible ? "opacity-100" : "opacity-0"
        }`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 z-50 h-full w-[420px] max-w-[100vw] bg-white shadow-xl
          flex flex-col transform transition-transform duration-200 ease-out
          ${visible ? "translate-x-0" : "translate-x-full"}`}
      >
        {/* Sticky header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
          <div className="flex items-center gap-2.5">
            <h2 className="text-base font-semibold text-gray-900">
              {isCreating ? "New task" : "Edit task"}
            </h2>
            {item && (
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  item.source === "manual"
                    ? "bg-blue-50 text-blue-600"
                    : item.source === "engagement_engine"
                    ? "bg-violet-50 text-violet-600"
                    : "bg-gray-100 text-gray-500"
                }`}
              >
                {item.source === "manual" ? "Manual" : item.source === "engagement_engine" ? "Engagement" : "AI extracted"}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
          >
            <XIcon />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Client selector (creation without client context) */}
          {isCreating && !clientId && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Client</label>
              <select
                value={selectedClientId}
                onChange={(e) => setSelectedClientId(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="">Select a client...</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Task text */}
          <div>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="What needs to be done?"
              rows={3}
              className="w-full resize-none rounded-lg border border-gray-200 px-3 py-2.5 text-[15px] text-gray-900 placeholder-gray-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>

          {/* Properties grid */}
          <div className="grid grid-cols-2 gap-4">
            {/* Status */}
            {!isCreating && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Status</label>
                <button
                  onClick={() => setStatus(status === "completed" ? "pending" : "completed")}
                  className={`w-full rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                    status === "completed"
                      ? "border-green-200 bg-green-50 text-green-700"
                      : "border-blue-200 bg-blue-50 text-blue-700"
                  }`}
                >
                  {status === "completed" ? "Completed" : "Pending"}
                </button>
              </div>
            )}

            {/* Priority */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Priority</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="">None</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>

            {/* Due date */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Due date</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>

            {/* Assigned to */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Assigned to</label>
              <select
                value={assignedTo}
                onChange={(e) => handleAssignmentChange(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="">Unassigned</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.user_name || m.user_email || m.user_id}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes..."
              className="w-full resize-none rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-700 placeholder-gray-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 min-h-[80px]"
            />
          </div>

          {/* Quarterly estimate email button */}
          {item && item.engagement_workflow_type === "quarterly_estimate" && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <div className="flex items-center gap-2 mb-1">
                <CalculatorIcon />
                <span className="text-xs font-semibold text-emerald-800">Quarterly Estimate Workflow</span>
              </div>
              {estimateEmailSent ? (
                <div className="space-y-2">
                  <p className="text-xs text-emerald-700">Estimate email sent! Mark this task as complete?</p>
                  <button
                    onClick={() => {
                      setStatus("completed");
                      setEstimateEmailSent(false);
                      handleSave();
                    }}
                    className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                  >
                    Mark Complete
                  </button>
                </div>
              ) : (
                <button
                  onClick={async () => {
                    // Fetch client details for SendEmailModal
                    try {
                      const clientData = await createClientsApi(getToken, activeOrg?.id).get(item.client_id);
                      setEstimateClient(clientData);
                      setShowEstimateEmail(true);
                    } catch {
                      setToast("Failed to load client");
                    }
                  }}
                  className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                >
                  <EnvelopeIcon />
                  {`Draft Q${parseQuarter(item.text) ?? "?"} Estimate Email`}
                </button>
              )}
            </div>
          )}

          {/* Metadata footer */}
          {item && (
            <div className="space-y-1 pt-2 border-t border-gray-100">
              <p className="text-[11px] text-gray-400">
                Created{" "}
                {new Date(item.created_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
                {item.source === "ai_extracted" && item.document_filename
                  ? ` · AI extracted from ${item.document_filename}`
                  : item.source === "manual"
                  ? " · Manually created"
                  : ""}
              </p>
              {item.updated_at && item.updated_at !== item.created_at && (
                <p className="text-[11px] text-gray-400">
                  Last updated {relativeTime(item.updated_at)}
                </p>
              )}
              {(item.client_name || clientId) && (
                <Link
                  href={`/dashboard/clients/${item.client_id}`}
                  className="text-[11px] text-blue-500 hover:underline"
                >
                  {item.client_name ?? "View client"} &rarr;
                </Link>
              )}
            </div>
          )}
        </div>

        {/* Sticky footer */}
        <div className="sticky bottom-0 z-10 border-t border-gray-200 bg-white px-6 pt-4 pb-4 flex items-center justify-between">
          <div>
            {!isCreating && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="text-sm text-red-500 hover:text-red-700 disabled:opacity-50"
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            )}
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !text.trim() || (isCreating && !clientId && !selectedClientId)}
            className="rounded-lg bg-amber-500 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving..." : isCreating ? "Create task" : "Save changes"}
          </button>
        </div>

        {/* Toast */}
        {toast && (
          <div className="absolute bottom-20 left-1/2 -translate-x-1/2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white shadow-lg">
            {toast}
          </div>
        )}
      </div>

      {/* Quarterly estimate email modal */}
      {showEstimateEmail && estimateClient && item && (
        <SendEmailModal
          clientId={item.client_id}
          clientName={estimateClient.name}
          clientEmail={estimateClient.email}
          initialQuarterly={{
            year: parseYear(item.text) ?? new Date().getFullYear(),
            quarter: parseQuarter(item.text) ?? 1,
          }}
          onClose={() => setShowEstimateEmail(false)}
          onSent={() => {
            setShowEstimateEmail(false);
            setEstimateEmailSent(true);
          }}
        />
      )}
    </>,
    document.body
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function parseQuarter(text: string): number | null {
  const m = text.match(/Q(\d)/);
  return m ? parseInt(m[1], 10) : null;
}

function parseYear(text: string): number | null {
  const m = text.match(/\((\d{4})\)/);
  return m ? parseInt(m[1], 10) : null;
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function XIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function CalculatorIcon() {
  return (
    <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 15.75V18m-7.5-6.75h.008v.008H8.25v-.008zm0 2.25h.008v.008H8.25v-.008zm0 2.25h.008v.008H8.25v-.008zm0 2.25h.008v.008H8.25v-.008zm2.498-6.75h.007v.008h-.007v-.008zm0 2.25h.007v.008h-.007v-.008zm0 2.25h.007v.008h-.007v-.008zm0 2.25h.007v.008h-.007v-.008zm2.504-6.75h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008v-.008zm1.498 2.25h.008v.008h-.008v-.008zm-1.498-6.75h.008v.008h-.008V18zM15.75 15.75h.008v.008h-.008v-.008zm0 2.25h.007v.008h-.007v-.008zM15 9.75a.75.75 0 00-.75.75v.008c0 .414.336.75.75.75h.008a.75.75 0 00.75-.75V10.5a.75.75 0 00-.75-.75H15zM4.5 19.5h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15A2.25 2.25 0 002.25 6.75v10.5A2.25 2.25 0 004.5 19.5zm6-10.125a1.875 1.875 0 11-3.75 0 1.875 1.875 0 013.75 0zm1.5-4.875h4.125a1.125 1.125 0 010 2.25H12a1.125 1.125 0 010-2.25z" />
    </svg>
  );
}

function EnvelopeIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  );
}
