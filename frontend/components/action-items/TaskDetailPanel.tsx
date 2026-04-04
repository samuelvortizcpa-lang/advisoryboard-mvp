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
                    : "bg-gray-100 text-gray-500"
                }`}
              >
                {item.source === "manual" ? "Manual" : "AI extracted"}
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

// ─── Icons ────────────────────────────────────────────────────────────────────

function XIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
