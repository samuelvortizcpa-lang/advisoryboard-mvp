"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

import { createJournalApi } from "@/lib/api";

const CATEGORIES = [
  { value: "", label: "Select category..." },
  { value: "income", label: "Income" },
  { value: "deductions", label: "Deductions" },
  { value: "family", label: "Family" },
  { value: "property", label: "Property" },
  { value: "employment", label: "Employment" },
  { value: "business", label: "Business" },
  { value: "investment", label: "Investment" },
  { value: "compliance", label: "Compliance" },
  { value: "general", label: "General" },
];

interface Props {
  clientId: string;
  onClose: () => void;
  onCreated: () => void;
}

export default function AddJournalEntry({ clientId, onClose, onCreated }: Props) {
  const { getToken } = useAuth();

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [isPinned, setIsPinned] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;

    setSaving(true);
    setError(null);
    try {
      const api = createJournalApi(getToken);
      await api.create(clientId, {
        title: title.trim(),
        content: content.trim() || undefined,
        entry_type: "manual",
        category: category || undefined,
        effective_date: effectiveDate || undefined,
        is_pinned: isPinned,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create entry");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />

      {/* Slide-over */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md">
        <div className="flex h-full flex-col bg-white shadow-xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <h2 className="text-base font-semibold text-gray-900">Add Journal Entry</h2>
            <button
              onClick={onClose}
              className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-500"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-y-auto">
            <div className="flex-1 space-y-5 px-6 py-5">
              {/* Title */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Client mentioned new rental property"
                  maxLength={200}
                  className="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  autoFocus
                />
              </div>

              {/* Content */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">Details</label>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Add any additional context..."
                  rows={5}
                  className="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Category */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">Category</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>

              {/* Effective Date */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">
                  When did this happen?
                </label>
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <p className="mt-1 text-xs text-gray-400">Optional — leave blank to use today</p>
              </div>

              {/* Pin toggle */}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setIsPinned(!isPinned)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    isPinned ? "bg-amber-500" : "bg-gray-200"
                  }`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                      isPinned ? "translate-x-4" : "translate-x-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm text-gray-700">Pin this entry</span>
              </div>

              {/* Error */}
              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {error}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-gray-200 px-6 py-4">
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!title.trim() || saving}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Save Entry"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
