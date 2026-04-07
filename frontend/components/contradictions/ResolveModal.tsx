"use client";

import { useState } from "react";

interface Props {
  title: string;
  description: string;
  onResolve: (note: string) => Promise<void>;
  onClose: () => void;
}

export default function ResolveModal({ title, description, onResolve, onClose }: Props) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleResolve() {
    if (!note.trim()) return;
    setSaving(true);
    try {
      await onResolve(note.trim());
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-base font-semibold text-gray-900">Resolve Contradiction</h2>

        <div className="mt-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-sm font-medium text-gray-800">{title}</p>
          <p className="mt-1 text-xs text-gray-500 leading-relaxed">{description}</p>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">
            How was this resolved?
          </label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Verified W-2 is correct; 1040 had a data entry error..."
            rows={3}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
          />
        </div>

        <div className="mt-5 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleResolve}
            disabled={saving || !note.trim()}
            className="inline-flex items-center gap-2 rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700 disabled:opacity-50"
          >
            {saving ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Resolving...
              </>
            ) : (
              "Resolve"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
