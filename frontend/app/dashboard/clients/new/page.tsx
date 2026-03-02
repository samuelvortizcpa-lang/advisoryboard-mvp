"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useState } from "react";

import { ClientCreateData, createClientsApi } from "@/lib/api";

const ENTITY_TYPES = [
  "LLC",
  "S-Corp",
  "C-Corp",
  "Partnership",
  "Sole Proprietorship",
  "Individual",
  "Non-Profit",
  "Trust",
  "Other",
];

type FormState = {
  name: string;
  email: string;
  business_name: string;
  entity_type: string;
  industry: string;
  notes: string;
};

const empty: FormState = {
  name: "",
  email: "",
  business_name: "",
  entity_type: "",
  industry: "",
  notes: "",
};

export default function NewClientPage() {
  const { getToken } = useAuth();
  const router = useRouter();

  const [form, setForm] = useState<FormState>(empty);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setField(field: keyof FormState) {
    return (
      e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
    ) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      // Omit empty optional strings so the backend gets null, not ""
      const payload: ClientCreateData = { name: form.name };
      if (form.email) payload.email = form.email;
      if (form.business_name) payload.business_name = form.business_name;
      if (form.entity_type) payload.entity_type = form.entity_type;
      if (form.industry) payload.industry = form.industry;
      if (form.notes) payload.notes = form.notes;

      await createClientsApi(getToken).create(payload);
      router.push("/dashboard/clients");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create client"
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center gap-2 text-sm">
          <Link
            href="/dashboard"
            className="font-semibold text-gray-900 hover:text-gray-600 transition-colors"
          >
            AdvisoryBoard
          </Link>
          <span className="text-gray-300">/</span>
          <Link
            href="/dashboard/clients"
            className="font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            Clients
          </Link>
          <span className="text-gray-300">/</span>
          <span className="font-medium text-gray-900">New</span>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <h1 className="mb-7 text-xl font-semibold text-gray-900">
          Add New Client
        </h1>

        {error && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
        >
          <Field label="Name" required>
            <input
              type="text"
              required
              value={form.name}
              onChange={setField("name")}
              placeholder="Jane Smith"
              className={inputCls}
            />
          </Field>

          <Field label="Email">
            <input
              type="email"
              value={form.email}
              onChange={setField("email")}
              placeholder="jane@example.com"
              className={inputCls}
            />
          </Field>

          <Field label="Business Name">
            <input
              type="text"
              value={form.business_name}
              onChange={setField("business_name")}
              placeholder="Acme LLC"
              className={inputCls}
            />
          </Field>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Entity Type">
              <select
                value={form.entity_type}
                onChange={setField("entity_type")}
                className={inputCls}
              >
                <option value="">Select type</option>
                {ENTITY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Industry">
              <input
                type="text"
                value={form.industry}
                onChange={setField("industry")}
                placeholder="Technology"
                className={inputCls}
              />
            </Field>
          </div>

          <Field label="Notes">
            <textarea
              value={form.notes}
              onChange={setField("notes")}
              rows={3}
              placeholder="Optional notes about this client…"
              className={`${inputCls} resize-none`}
            />
          </Field>

          <div className="flex items-center justify-end gap-3 border-t border-gray-100 pt-4">
            <Link
              href="/dashboard/clients"
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Spinner />
                  Saving…
                </>
              ) : (
                "Save Client"
              )}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

// ─── Shared sub-components ────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500";

function Field({
  label,
  required = false,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
  );
}
