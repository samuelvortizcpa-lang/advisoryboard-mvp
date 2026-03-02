"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { Client, ClientUpdateData, createClientsApi } from "@/lib/api";

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

type EditForm = {
  name: string;
  email: string;
  business_name: string;
  entity_type: string;
  industry: string;
  notes: string;
};

function clientToForm(c: Client): EditForm {
  return {
    name: c.name,
    email: c.email ?? "",
    business_name: c.business_name ?? "",
    entity_type: c.entity_type ?? "",
    industry: c.industry ?? "",
    notes: c.notes ?? "",
  };
}

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { getToken } = useAuth();
  const router = useRouter();

  const [client, setClient] = useState<Client | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<EditForm>({
    name: "",
    email: "",
    business_name: "",
    entity_type: "",
    industry: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    createClientsApi(getToken)
      .get(id)
      .then((c) => {
        setClient(c);
        setEditForm(clientToForm(c));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, getToken]);

  function setField(field: keyof EditForm) {
    return (
      e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
    ) => setEditForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  async function handleUpdate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      // Only send changed fields; strip empty optional strings → undefined
      const payload: ClientUpdateData = { name: editForm.name };
      payload.email = editForm.email || undefined;
      payload.business_name = editForm.business_name || undefined;
      payload.entity_type = editForm.entity_type || undefined;
      payload.industry = editForm.industry || undefined;
      payload.notes = editForm.notes || undefined;

      const updated = await createClientsApi(getToken).update(id, payload);
      setClient(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await createClientsApi(getToken).delete(id);
      router.push("/dashboard/clients");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete client");
      setShowDeleteModal(false);
      setDeleting(false);
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
          {client && (
            <>
              <span className="text-gray-300">/</span>
              <span className="max-w-[200px] truncate font-medium text-gray-900">
                {client.name}
              </span>
            </>
          )}
        </div>
      </header>

      {/* Main */}
      <main className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Loading */}
        {loading && (
          <div className="flex justify-center py-20">
            <div className="h-6 w-6 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* ── View mode ────────────────────────────────────────────────── */}
        {!loading && client && !editing && (
          <>
            <div className="mb-6 flex items-start justify-between">
              <div>
                <h1 className="text-xl font-semibold text-gray-900">
                  {client.name}
                </h1>
                {client.business_name && (
                  <p className="mt-0.5 text-sm text-gray-500">
                    {client.business_name}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setEditing(true)}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => setShowDeleteModal(true)}
                  className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <dl className="divide-y divide-gray-100">
                <DetailRow label="Email" value={client.email} />
                <DetailRow label="Business" value={client.business_name} />
                <DetailRow label="Entity Type" value={client.entity_type} />
                <DetailRow label="Industry" value={client.industry} />
                {client.notes && (
                  <div className="px-6 py-4">
                    <dt className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
                      Notes
                    </dt>
                    <dd className="whitespace-pre-wrap text-sm text-gray-700">
                      {client.notes}
                    </dd>
                  </div>
                )}
                <div className="flex gap-8 px-6 py-3">
                  <Timestamp label="Added" iso={client.created_at} />
                  <Timestamp label="Updated" iso={client.updated_at} />
                </div>
              </dl>
            </div>
          </>
        )}

        {/* ── Edit mode ────────────────────────────────────────────────── */}
        {!loading && client && editing && (
          <>
            <h1 className="mb-6 text-xl font-semibold text-gray-900">
              Edit Client
            </h1>

            <form
              onSubmit={handleUpdate}
              className="space-y-5 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
            >
              <Field label="Name" required>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={setField("name")}
                  className={inputCls}
                />
              </Field>

              <Field label="Email">
                <input
                  type="email"
                  value={editForm.email}
                  onChange={setField("email")}
                  className={inputCls}
                />
              </Field>

              <Field label="Business Name">
                <input
                  type="text"
                  value={editForm.business_name}
                  onChange={setField("business_name")}
                  className={inputCls}
                />
              </Field>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Entity Type">
                  <select
                    value={editForm.entity_type}
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
                    value={editForm.industry}
                    onChange={setField("industry")}
                    className={inputCls}
                  />
                </Field>
              </div>

              <Field label="Notes">
                <textarea
                  value={editForm.notes}
                  onChange={setField("notes")}
                  rows={3}
                  className={`${inputCls} resize-none`}
                />
              </Field>

              <div className="flex items-center justify-end gap-3 border-t border-gray-100 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setEditForm(clientToForm(client));
                    setError(null);
                  }}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  Cancel
                </button>
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
                    "Save Changes"
                  )}
                </button>
              </div>
            </form>
          </>
        )}
      </main>

      {/* ── Delete confirmation modal ─────────────────────────────────── */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">
              Delete client?
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              This will permanently delete{" "}
              <strong>{client?.name}</strong> and all associated documents and
              interactions. This cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {deleting ? (
                  <>
                    <Spinner />
                    Deleting…
                  </>
                ) : (
                  "Delete"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
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

function DetailRow({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="flex items-start gap-6 px-6 py-4">
      <dt className="w-28 shrink-0 pt-0.5 text-xs font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </dt>
      <dd className="text-sm text-gray-900">{value || "—"}</dd>
    </div>
  );
}

function Timestamp({ label, iso }: { label: string; iso: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-xs text-gray-600">
        {new Date(iso).toLocaleDateString("en-US", {
          year: "numeric",
          month: "short",
          day: "numeric",
        })}
      </p>
    </div>
  );
}

function Spinner() {
  return (
    <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
  );
}
