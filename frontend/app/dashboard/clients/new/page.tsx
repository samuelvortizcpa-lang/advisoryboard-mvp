"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { ClientCreateData, ClientType, createClientTypesApi, createClientsApi } from "@/lib/api";

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

const TYPE_COLOR_CLASSES: Record<string, string> = {
  blue: "bg-blue-100 text-blue-700",
  green: "bg-green-100 text-green-700",
  purple: "bg-purple-100 text-purple-700",
  red: "bg-red-100 text-red-700",
  gray: "bg-gray-100 text-gray-700",
};

type FormState = {
  name: string;
  email: string;
  business_name: string;
  entity_type: string;
  industry: string;
  notes: string;
  client_type_id: string;
  custom_instructions: string;
};

const empty: FormState = {
  name: "",
  email: "",
  business_name: "",
  entity_type: "",
  industry: "",
  notes: "",
  client_type_id: "",
  custom_instructions: "",
};

export default function NewClientPage() {
  const { getToken } = useAuth();
  const router = useRouter();

  const [form, setForm] = useState<FormState>(empty);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [clientTypes, setClientTypes] = useState<ClientType[]>([]);

  useEffect(() => {
    createClientTypesApi(getToken)
      .list()
      .then((res) => setClientTypes(res.types))
      .catch(() => {/* non-fatal */});
  }, [getToken]);

  function setField(field: keyof FormState) {
    return (
      e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
    ) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  const selectedType = clientTypes.find((t) => t.id === form.client_type_id) ?? null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const payload: ClientCreateData = { name: form.name };
      if (form.email) payload.email = form.email;
      if (form.business_name) payload.business_name = form.business_name;
      if (form.entity_type) payload.entity_type = form.entity_type;
      if (form.industry) payload.industry = form.industry;
      if (form.notes) payload.notes = form.notes;
      if (form.client_type_id) payload.client_type_id = form.client_type_id;
      if (form.custom_instructions) payload.custom_instructions = form.custom_instructions;

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
    <div className="px-8 py-8">
      <div className="max-w-2xl">
        <h1 className="mb-7 text-xl font-semibold text-gray-900">
          Add New Client
        </h1>

        {error && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
            {error.toLowerCase().includes("client limit") && (
              <Link
                href="/dashboard/settings/subscriptions"
                className="ml-2 font-medium text-blue-600 underline hover:text-blue-700"
              >
                Upgrade your plan
              </Link>
            )}
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

          {/* Client Type */}
          <Field label="Client Type">
            <div className="flex items-center gap-2">
              <select
                value={form.client_type_id}
                onChange={setField("client_type_id")}
                className={`${inputCls} flex-1`}
              >
                <option value="">No type selected</option>
                {clientTypes.map((ct) => (
                  <option key={ct.id} value={ct.id}>
                    {ct.name}
                  </option>
                ))}
              </select>
              {selectedType && (
                <span
                  className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    TYPE_COLOR_CLASSES[selectedType.color] ?? "bg-gray-100 text-gray-700"
                  }`}
                >
                  {selectedType.name}
                </span>
              )}
            </div>
            {selectedType && (
              <p className="mt-1 text-xs text-gray-500">{selectedType.description}</p>
            )}
          </Field>

          {/* Custom Instructions */}
          <Field label="Custom AI Instructions">
            <textarea
              value={form.custom_instructions}
              onChange={setField("custom_instructions")}
              rows={3}
              placeholder="e.g., Always focus on real estate investments for this client"
              className={`${inputCls} resize-none`}
            />
            <p className="mt-1 text-xs text-gray-500">
              Custom AI instructions specific to this client (optional). These are appended to the client type prompt.
            </p>
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
      </div>
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
