"use client";

import { useAuth } from "@clerk/nextjs";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ChangeEvent, FormEvent, Suspense, useEffect, useState } from "react";

import {
  Client,
  ClientAccessSummary,
  ClientBrief,
  ClientType,
  ClientUpdateData,
  CompareResponse,
  ComparisonType,
  Document,
  OrgMember,
  ProfileFlags,
  createActionItemsApi,
  createBriefsApi,
  createClientTypesApi,
  createClientsApi,
  createDocumentsApi,
  createOrganizationsApi,
  createRagApi,
  createStrategiesApi,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import ActionItemList from "@/components/action-items/ActionItemList";
import DeadlineWidget from "@/components/action-items/DeadlineWidget";
import BriefPanel from "@/components/briefs/BriefPanel";
import DocumentList from "@/components/documents/DocumentList";
import DocumentComparisonReport from "@/components/documents/DocumentComparisonReport";
import DocumentUpload from "@/components/documents/DocumentUpload";
import ClientChat from "@/components/rag/ClientChat";
import CalendarView from "@/components/timeline/CalendarView";
import AssignedTeam from "@/components/clients/AssignedTeam";
import ConsentBanner from "@/components/consent/ConsentBanner";
import ProfileFlagsRow from "@/components/strategies/ProfileFlags";
import StrategyChecklist from "@/components/strategies/StrategyChecklist";
import Timeline from "@/components/timeline/Timeline";

// ─── Constants ────────────────────────────────────────────────────────────────

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

type TabId = "overview" | "documents" | "actions" | "chat" | "timeline" | "strategies" | "access";

const BASE_TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "documents", label: "Documents" },
  { id: "actions", label: "Actions" },
  { id: "strategies", label: "Tax Strategies" },
  { id: "chat", label: "Chat" },
  { id: "timeline", label: "Timeline" },
];

// ─── Types ────────────────────────────────────────────────────────────────────

type EditForm = {
  name: string;
  email: string;
  business_name: string;
  entity_type: string;
  industry: string;
  notes: string;
  client_type_id: string;
  custom_instructions: string;
};

function clientToForm(c: Client): EditForm {
  return {
    name: c.name,
    email: c.email ?? "",
    business_name: c.business_name ?? "",
    entity_type: c.entity_type ?? "",
    industry: c.industry ?? "",
    notes: c.notes ?? "",
    client_type_id: c.client_type_id ?? "",
    custom_instructions: c.custom_instructions ?? "",
  };
}

// ─── Main content (needs Suspense for useSearchParams) ────────────────────────

function ClientDetailContent() {
  const { id } = useParams<{ id: string }>();
  const { getToken } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const activeTab = (searchParams.get("tab") ?? "overview") as TabId;

  // ── Client state ────────────────────────────────────────────────────────────
  const [client, setClient] = useState<Client | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Edit state ──────────────────────────────────────────────────────────────
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<EditForm>({
    name: "",
    email: "",
    business_name: "",
    entity_type: "",
    industry: "",
    notes: "",
    client_type_id: "",
    custom_instructions: "",
  });
  const [saving, setSaving] = useState(false);
  const [clientTypes, setClientTypes] = useState<ClientType[]>([]);

  // ── Delete state ────────────────────────────────────────────────────────────
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // ── Documents state ─────────────────────────────────────────────────────────
  const [documents, setDocuments] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [docsError, setDocsError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);

  // ── Document comparison state ───────────────────────────────────────────────
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [comparisonType, setComparisonType] = useState<ComparisonType>("summary");
  const [comparing, setComparing] = useState(false);
  const [comparisonResult, setComparisonResult] = useState<CompareResponse | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  // ── Brief state ────────────────────────────────────────────────────────────
  const [brief, setBrief] = useState<ClientBrief | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [briefError, setBriefError] = useState<string | null>(null);
  const [showBriefPanel, setShowBriefPanel] = useState(false);

  // ── Shared refresh key ──────────────────────────────────────────────────────
  const [actionItemsRefreshKey, setActionItemsRefreshKey] = useState(0);

  // ── Organization / team access state ────────────────────────────────────────
  const { activeOrg, isAdmin: isOrgAdmin } = useOrg();
  const org = activeOrg?.org_type === "firm" ? activeOrg : null;
  const [accessSummary, setAccessSummary] = useState<ClientAccessSummary | null>(null);
  const [accessLoading, setAccessLoading] = useState(false);
  const [accessActionLoading, setAccessActionLoading] = useState<string | null>(null);
  const [accessFeedback, setAccessFeedback] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [orgMembers, setOrgMembers] = useState<OrgMember[]>([]);
  const [showAddAccess, setShowAddAccess] = useState(false);
  const [openConfirm, setOpenConfirm] = useState(false);

  const isFirmAdmin = org !== null && isOrgAdmin;

  // ── Strategy state ─────────────────────────────────────────────────────────
  const [implementedCount, setImplementedCount] = useState<number | null>(null);
  const [profileFlags, setProfileFlags] = useState<ProfileFlags>({
    has_business_entity: false,
    has_real_estate: false,
    is_real_estate_professional: false,
    has_high_income: false,
    has_estate_planning: false,
    is_medical_professional: false,
    has_retirement_plans: false,
    has_investments: false,
    has_employees: false,
  });

  // ── Overview summary data ───────────────────────────────────────────────────
  const [pendingActionsCount, setPendingActionsCount] = useState<number | null>(null);
  const [nextDeadline, setNextDeadline] = useState<string | null | undefined>(undefined);
  const [lastChatDate, setLastChatDate] = useState<string | null | undefined>(undefined);

  // ── Fetch all data on mount ─────────────────────────────────────────────────
  useEffect(() => {
    createClientsApi(getToken)
      .get(id)
      .then((c) => {
        setClient(c);
        setEditForm(clientToForm(c));
        // Extract profile flags from client data
        const clientAny = c as unknown as Record<string, unknown>;
        setProfileFlags({
          has_business_entity: clientAny.has_business_entity === true,
          has_real_estate: clientAny.has_real_estate === true,
          is_real_estate_professional: clientAny.is_real_estate_professional === true,
          has_high_income: clientAny.has_high_income === true,
          has_estate_planning: clientAny.has_estate_planning === true,
          is_medical_professional: clientAny.is_medical_professional === true,
          has_retirement_plans: clientAny.has_retirement_plans === true,
          has_investments: clientAny.has_investments === true,
          has_employees: clientAny.has_employees === true,
        });
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));

    // Load strategy implemented count for tab badge
    createStrategiesApi(getToken)
      .fetchChecklist(id, new Date().getFullYear())
      .then((res) => setImplementedCount(res.summary.total_implemented))
      .catch(() => {/* non-fatal */});

    createDocumentsApi(getToken)
      .list(id)
      .then((res) => setDocuments(res.items))
      .catch((e: Error) => setDocsError(e.message))
      .finally(() => setDocsLoading(false));

    createClientTypesApi(getToken)
      .list()
      .then((res) => setClientTypes(res.types))
      .catch(() => {/* non-fatal */});

    // Overview: pending actions count + next deadline
    createActionItemsApi(getToken)
      .list(id, "pending")
      .then((res) => {
        setPendingActionsCount(res.total);
        const deadlines = res.items
          .filter((item) => item.due_date)
          .map((item) => item.due_date!)
          .sort();
        setNextDeadline(deadlines[0] ?? null);
      })
      .catch(() => {
        setPendingActionsCount(null);
        setNextDeadline(null);
      });

    // Overview: last chat date
    createRagApi(getToken)
      .getChatHistory(id)
      .then((res) => {
        const msgs = res.messages;
        if (msgs.length > 0) {
          const last = msgs[msgs.length - 1] as { created_at?: string } & typeof msgs[0];
          setLastChatDate(last.created_at ?? null);
        } else {
          setLastChatDate(null);
        }
      })
      .catch(() => setLastChatDate(null));
  }, [id, getToken]);

  // Load team access data when org is available
  useEffect(() => {
    if (!org) return;
    loadAccessData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org, id]);

  function loadAccessData() {
    if (!org) return;
    setAccessLoading(true);
    const api = createOrganizationsApi(getToken);
    Promise.all([
      api.fetchClientAccess(org.id, id),
      api.listMembers(org.id),
    ])
      .then(([access, members]) => {
        setAccessSummary(access);
        setOrgMembers(members.filter((m) => m.is_active));
      })
      .catch(() => {/* non-fatal */})
      .finally(() => setAccessLoading(false));
  }

  // Build tabs — add "Team Access" if firm admin
  const TABS = isFirmAdmin
    ? [...BASE_TABS, { id: "access" as TabId, label: "Team Access" }]
    : BASE_TABS;

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function navigateToTab(tab: TabId) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.push(`?${params.toString()}`, { scroll: false });
  }

  function setField(field: keyof EditForm) {
    return (
      e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
    ) => setEditForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  const selectedEditType = clientTypes.find((t) => t.id === editForm.client_type_id) ?? null;

  // ── Handlers ─────────────────────────────────────────────────────────────────

  async function handleUpdate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload: ClientUpdateData = { name: editForm.name };
      payload.email = editForm.email || undefined;
      payload.business_name = editForm.business_name || undefined;
      payload.entity_type = editForm.entity_type || undefined;
      payload.industry = editForm.industry || undefined;
      payload.notes = editForm.notes || undefined;
      payload.client_type_id = editForm.client_type_id || null;
      payload.custom_instructions = editForm.custom_instructions || null;

      const updated = await createClientsApi(getToken).update(id, payload);
      setClient(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  async function handleDocumentDownload(doc: Document) {
    setDownloading(doc.id);
    try {
      await createDocumentsApi(getToken).download(doc.id, doc.filename);
    } catch (err) {
      setDocsError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  }

  async function handleDocumentDelete(doc: Document) {
    setDeletingDocId(doc.id);
    try {
      await createDocumentsApi(getToken).delete(doc.id);
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
    } catch (err) {
      setDocsError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeletingDocId(null);
    }
  }

  function handleToggleDocSelect(docId: string) {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
    setComparisonResult(null);
    setComparisonError(null);
  }

  async function handleCompare() {
    const ids = Array.from(selectedDocIds);
    if (ids.length < 2) return;
    setComparing(true);
    setComparisonResult(null);
    setComparisonError(null);
    try {
      const result = await createRagApi(getToken).compare(id, ids, comparisonType);
      setComparisonResult(result);
    } catch (err) {
      setComparisonError(err instanceof Error ? err.message : "Comparison failed");
    } finally {
      setComparing(false);
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

  async function handleGenerateBrief() {
    setBriefLoading(true);
    setBriefError(null);
    try {
      const result = await createBriefsApi(getToken).generate(id);
      setBrief(result);
      setShowBriefPanel(true);
    } catch (err) {
      setBriefError(err instanceof Error ? err.message : "Failed to generate brief");
    } finally {
      setBriefLoading(false);
    }
  }

  // ── Team access handlers ────────────────────────────────────────────────────

  function showAccessFeedback(message: string, type: "success" | "error") {
    setAccessFeedback({ message, type });
    setTimeout(() => setAccessFeedback(null), 3000);
  }

  async function handleRestrictAccess() {
    if (!org) return;
    setAccessActionLoading("restrict");
    try {
      const result = await createOrganizationsApi(getToken).restrictClient(org.id, id);
      setAccessSummary(result);
      showAccessFeedback("Access restricted to assigned members", "success");
    } catch (err) {
      showAccessFeedback(err instanceof Error ? err.message : "Failed to restrict access", "error");
    } finally {
      setAccessActionLoading(null);
    }
  }

  async function handleOpenAccess() {
    if (!org || !accessSummary) return;
    setAccessActionLoading("open");
    setOpenConfirm(false);
    try {
      const api = createOrganizationsApi(getToken);
      // Delete all access records to revert to open mode
      for (const rec of accessSummary.records) {
        await api.revokeClientAccess(org.id, id, rec.user_id);
      }
      setAccessSummary({ mode: "open", records: [] });
      showAccessFeedback("Access opened to all team members", "success");
    } catch (err) {
      showAccessFeedback(err instanceof Error ? err.message : "Failed to open access", "error");
      loadAccessData();
    } finally {
      setAccessActionLoading(null);
    }
  }

  async function handleChangeAccessLevel(userId: string, newLevel: string) {
    if (!org) return;
    setAccessActionLoading(userId);
    try {
      await createOrganizationsApi(getToken).grantClientAccess(org.id, id, userId, newLevel);
      showAccessFeedback("Access level updated", "success");
      loadAccessData();
    } catch (err) {
      showAccessFeedback(err instanceof Error ? err.message : "Failed to update access", "error");
    } finally {
      setAccessActionLoading(null);
    }
  }

  async function handleGrantAccess(userId: string) {
    if (!org) return;
    setAccessActionLoading(userId);
    try {
      await createOrganizationsApi(getToken).grantClientAccess(org.id, id, userId, "full");
      showAccessFeedback("Access granted", "success");
      setShowAddAccess(false);
      loadAccessData();
    } catch (err) {
      showAccessFeedback(err instanceof Error ? err.message : "Failed to grant access", "error");
    } finally {
      setAccessActionLoading(null);
    }
  }

  async function handleRevokeAccess(userId: string) {
    if (!org) return;
    setAccessActionLoading(userId);
    try {
      await createOrganizationsApi(getToken).revokeClientAccess(org.id, id, userId);
      showAccessFeedback("Access revoked", "success");
      loadAccessData();
    } catch (err) {
      showAccessFeedback(err instanceof Error ? err.message : "Failed to revoke access", "error");
    } finally {
      setAccessActionLoading(null);
    }
  }

  // Unassigned members (not in current access records)
  const assignedUserIds = new Set(accessSummary?.records.map((r) => r.user_id) ?? []);
  const unassignedMembers = orgMembers.filter((m) => !assignedUserIds.has(m.user_id));

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Loading ───────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      )}

      {/* ── Error banner ──────────────────────────────────────────────────── */}
      {error && (
        <div className="px-8 pt-6">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        </div>
      )}

      {/* ── Edit mode (full-page form, no tabs) ───────────────────────────── */}
      {!loading && client && editing && (
        <main className="max-w-2xl mx-auto px-8 py-8">
          <h1 className="mb-6 text-xl font-semibold text-gray-900">Edit Client</h1>

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

            <Field label="Client Type">
              <div className="flex items-center gap-2">
                <select
                  value={editForm.client_type_id}
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
                {selectedEditType && (
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      TYPE_COLOR_CLASSES[selectedEditType.color] ?? "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {selectedEditType.name}
                  </span>
                )}
              </div>
              {selectedEditType && (
                <p className="mt-1 text-xs text-gray-500">{selectedEditType.description}</p>
              )}
            </Field>

            <Field label="Custom AI Instructions">
              <textarea
                value={editForm.custom_instructions}
                onChange={setField("custom_instructions")}
                rows={3}
                placeholder="e.g., Always focus on real estate investments for this client"
                className={`${inputCls} resize-none`}
              />
              <p className="mt-1 text-xs text-gray-500">
                Custom AI instructions specific to this client (optional).
              </p>
            </Field>

            <div className="flex items-center justify-end gap-3 border-t border-gray-100 pt-4">
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setEditForm(clientToForm(client));
                  setError(null);
                }}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
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
        </main>
      )}

      {/* ── View mode: client header + tab nav + tab content ──────────────── */}
      {!loading && client && !editing && (
        <>
          {/* ── Client entity header ──────────────────────────────────────── */}
          <div className="bg-white border-b border-gray-100">
            <div className="px-8 py-5 flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2.5 flex-wrap">
                  <h1 className="text-[28px] font-bold leading-tight text-gray-900">
                    {client.name}
                  </h1>
                  {client.client_type && <ClientTypeBadge type={client.client_type} />}
                </div>
                {client.business_name && (
                  <p className="mt-1 text-sm text-gray-500">{client.business_name}</p>
                )}
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={handleGenerateBrief}
                  disabled={briefLoading}
                  className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {briefLoading ? (
                    <>
                      <BriefSpinner />
                      Generating…
                    </>
                  ) : (
                    <>
                      <BriefIcon />
                      Generate Brief
                    </>
                  )}
                </button>
                <button
                  onClick={() => setEditing(true)}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                >
                  Edit
                </button>
                <button
                  onClick={() => setShowDeleteModal(true)}
                  className="rounded-md border border-red-200 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>

          {/* ── Assigned team (org admins only) ──────────────────────────── */}
          <AssignedTeam clientId={id} />

          {/* ── 7216 consent banner ────────────────────────────────────────── */}
          <ConsentBanner
            clientId={id}
            clientName={client.name}
            clientEmail={client.email}
            getToken={getToken}
          />

          {/* ── Tab navigation bar ────────────────────────────────────────── */}
          <div className="sticky top-[56px] z-10 bg-white border-b border-gray-200 shadow-sm">
            <div className="px-8">
              <nav className="-mb-px flex overflow-x-auto" aria-label="Tabs">
                {TABS.map((tab) => {
                  const isActive = activeTab === tab.id;
                  const badge =
                    tab.id === "documents" && !docsLoading && documents.length > 0
                      ? documents.length
                      : tab.id === "actions" && pendingActionsCount !== null && pendingActionsCount > 0
                      ? pendingActionsCount
                      : tab.id === "strategies" && implementedCount !== null && implementedCount > 0
                      ? implementedCount
                      : null;

                  return (
                    <button
                      key={tab.id}
                      onClick={() => navigateToTab(tab.id)}
                      className={`flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-3.5 text-sm font-medium transition-colors ${
                        isActive
                          ? "border-blue-600 text-blue-600"
                          : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
                      }`}
                    >
                      {tab.label}
                      {badge !== null && (
                        <span
                          className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-medium ${
                            isActive
                              ? "bg-blue-100 text-blue-600"
                              : "bg-gray-100 text-gray-500"
                          }`}
                        >
                          {badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </nav>
            </div>
          </div>

          {/* ── Tab content ───────────────────────────────────────────────── */}
          <main className="px-8 py-8">

            {/* ── Overview ──────────────────────────────────────────────── */}
            {activeTab === "overview" && (
              <div className="space-y-6">
                {/* Summary cards — always 4 in a row */}
                <div className="grid grid-cols-4 gap-4">

                  {/* Documents */}
                  <button
                    onClick={() => navigateToTab("documents")}
                    className="group rounded-xl border border-gray-200 border-l-4 border-l-blue-500 bg-white p-5 text-left shadow-sm transition-all hover:shadow-md"
                  >
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600 transition-colors group-hover:bg-blue-100">
                      <OverviewDocIcon />
                    </div>
                    <p className="text-2xl font-bold text-gray-900">
                      {docsLoading ? <span className="text-gray-300">—</span> : documents.length}
                    </p>
                    <p className="mt-0.5 text-sm font-medium text-gray-500">Documents</p>
                    <p className="mt-2 text-xs text-blue-600 group-hover:underline">
                      View all →
                    </p>
                  </button>

                  {/* Pending Actions */}
                  <button
                    onClick={() => navigateToTab("actions")}
                    className="group rounded-xl border border-gray-200 border-l-4 border-l-amber-500 bg-white p-5 text-left shadow-sm transition-all hover:shadow-md"
                  >
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-amber-600 transition-colors group-hover:bg-amber-100">
                      <OverviewChecklistIcon />
                    </div>
                    <p className="text-2xl font-bold text-gray-900">
                      {pendingActionsCount === null ? (
                        <span className="text-gray-300">—</span>
                      ) : (
                        pendingActionsCount
                      )}
                    </p>
                    <p className="mt-0.5 text-sm font-medium text-gray-500">Pending Actions</p>
                    <p className="mt-2 text-xs text-amber-600 group-hover:underline">
                      Review →
                    </p>
                  </button>

                  {/* Next Deadline */}
                  <button
                    onClick={() => navigateToTab("actions")}
                    className="group rounded-xl border border-gray-200 border-l-4 border-l-red-400 bg-white p-5 text-left shadow-sm transition-all hover:shadow-md"
                  >
                    <div
                      className={`mb-3 flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
                        nextDeadline && isOverdue(nextDeadline)
                          ? "bg-red-100 text-red-600 group-hover:bg-red-200"
                          : "bg-red-50 text-red-400 group-hover:bg-red-100"
                      }`}
                    >
                      <OverviewCalendarIcon />
                    </div>
                    <p
                      className={`text-lg font-bold leading-tight ${
                        nextDeadline && isOverdue(nextDeadline)
                          ? "text-red-600"
                          : "text-gray-900"
                      }`}
                    >
                      {nextDeadline === undefined ? (
                        <span className="text-gray-300 text-2xl">—</span>
                      ) : nextDeadline ? (
                        formatDate(nextDeadline)
                      ) : (
                        <span className="text-gray-400 text-base">None</span>
                      )}
                    </p>
                    <p className="mt-0.5 text-sm font-medium text-gray-500">Next Deadline</p>
                    <p
                      className={`mt-2 text-xs group-hover:underline ${
                        nextDeadline && isOverdue(nextDeadline)
                          ? "text-red-500"
                          : "text-gray-400"
                      }`}
                    >
                      {nextDeadline && isOverdue(nextDeadline) ? "Overdue!" : "View actions →"}
                    </p>
                  </button>

                  {/* Last Chat */}
                  <button
                    onClick={() => navigateToTab("chat")}
                    className="group rounded-xl border border-gray-200 border-l-4 border-l-purple-500 bg-white p-5 text-left shadow-sm transition-all hover:shadow-md"
                  >
                    <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-purple-50 text-purple-600 transition-colors group-hover:bg-purple-100">
                      <OverviewChatIcon />
                    </div>
                    <p className="text-lg font-bold leading-tight text-gray-900">
                      {lastChatDate === undefined ? (
                        <span className="text-gray-300 text-2xl">—</span>
                      ) : lastChatDate ? (
                        formatRelativeTime(lastChatDate)
                      ) : (
                        <span className="text-gray-400 text-base">No chats yet</span>
                      )}
                    </p>
                    <p className="mt-0.5 text-sm font-medium text-gray-500">Last Chat</p>
                    <p className="mt-2 text-xs text-purple-600 group-hover:underline">
                      Open chat →
                    </p>
                  </button>
                </div>

                {/* Deadline widget */}
                <DeadlineWidget clientId={id} refreshKey={actionItemsRefreshKey} />

                {/* Client details card */}
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
                    {client.custom_instructions && (
                      <div className="px-6 py-4">
                        <dt className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
                          Custom AI Instructions
                        </dt>
                        <dd className="whitespace-pre-wrap text-sm text-gray-700">
                          {client.custom_instructions}
                        </dd>
                      </div>
                    )}
                    <div className="flex gap-8 px-6 py-3">
                      <Timestamp label="Added" iso={client.created_at} />
                      <Timestamp label="Updated" iso={client.updated_at} />
                    </div>
                  </dl>
                </div>
              </div>
            )}

            {/* ── Documents ─────────────────────────────────────────────── */}
            {activeTab === "documents" && (
              <div>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-base font-semibold text-gray-900">Documents</h2>
                  {documents.length >= 2 && (
                    <span className="text-xs text-gray-400">Select 2+ to compare</span>
                  )}
                </div>

                <DocumentUpload
                  clientId={id}
                  onUploaded={(doc) => {
                    setDocuments((prev) => [doc, ...prev]);
                    setTimeout(() => setActionItemsRefreshKey((k) => k + 1), 15_000);
                  }}
                />

                <div className="mt-4 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm px-4">
                  {docsLoading ? (
                    <div className="flex justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                    </div>
                  ) : docsError ? (
                    <p className="py-6 text-center text-sm text-red-600">{docsError}</p>
                  ) : (
                    <DocumentList
                      documents={documents}
                      onDownload={handleDocumentDownload}
                      onDelete={handleDocumentDelete}
                      downloading={downloading}
                      deleting={deletingDocId}
                      selectedIds={selectedDocIds}
                      onToggleSelect={handleToggleDocSelect}
                    />
                  )}
                </div>

                {/* Comparison toolbar */}
                {selectedDocIds.size >= 2 && (
                  <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
                    <span className="text-xs font-medium text-blue-700">
                      {selectedDocIds.size} documents selected
                    </span>

                    <select
                      value={comparisonType}
                      onChange={(e) => setComparisonType(e.target.value as ComparisonType)}
                      className="rounded-md border border-blue-200 bg-white px-3 py-1.5 text-xs text-gray-700 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    >
                      <option value="summary">Summary</option>
                      <option value="changes">Changes</option>
                      <option value="financial">Financial</option>
                    </select>

                    <button
                      onClick={handleCompare}
                      disabled={comparing}
                      className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {comparing ? (
                        <>
                          <CompareSpinner />
                          Comparing…
                        </>
                      ) : (
                        "Compare"
                      )}
                    </button>

                    <button
                      onClick={() => {
                        setSelectedDocIds(new Set());
                        setComparisonResult(null);
                        setComparisonError(null);
                      }}
                      className="ml-auto text-xs text-blue-400 transition-colors hover:text-blue-600"
                    >
                      Clear selection
                    </button>
                  </div>
                )}

                {comparisonError && (
                  <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {comparisonError}
                  </div>
                )}

                {comparisonResult && (
                  <DocumentComparisonReport
                    comparisonType={comparisonResult.comparison_type}
                    documents={comparisonResult.documents}
                    report={comparisonResult.report}
                    onClose={() => setComparisonResult(null)}
                  />
                )}
              </div>
            )}

            {/* ── Actions ───────────────────────────────────────────────── */}
            {activeTab === "actions" && (
              <ActionItemList
                clientId={id}
                documentCount={documents.length}
                refreshKey={actionItemsRefreshKey}
              />
            )}

            {/* ── Tax Strategies ──────────────────────────────────────── */}
            {activeTab === "strategies" && (
              <div className="space-y-4">
                <ProfileFlagsRow
                  clientId={id}
                  initialFlags={profileFlags}
                  onFlagsChange={setProfileFlags}
                />
                <StrategyChecklist clientId={id} profileFlags={profileFlags} />
              </div>
            )}

            {/* ── Chat ──────────────────────────────────────────────────── */}
            {activeTab === "chat" && (
              <div>
                <h2 className="mb-4 text-base font-semibold text-gray-900">Ask AI</h2>
                <ClientChat clientId={id} documentCount={documents.length} />
              </div>
            )}

            {/* ── Timeline ──────────────────────────────────────────────── */}
            {activeTab === "timeline" && (
              <div className="space-y-8">
                <CalendarView clientId={id} refreshKey={actionItemsRefreshKey} />
                <Timeline
                  clientId={id}
                  refreshKey={actionItemsRefreshKey}
                  onDocumentClick={() => navigateToTab("documents")}
                  onActionItemClick={() => navigateToTab("actions")}
                />
              </div>
            )}

            {/* ── Team Access ───────────────────────────────────────────── */}
            {activeTab === "access" && isFirmAdmin && (
              <div className="space-y-6">
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-gray-900">Team Access</h2>
                    <p className="mt-1 text-sm text-gray-500">
                      {accessSummary?.mode === "restricted"
                        ? "Access is restricted to assigned members"
                        : "This client is accessible to all team members"}
                    </p>
                  </div>
                  <div>
                    {accessSummary?.mode === "open" ? (
                      <button
                        onClick={handleRestrictAccess}
                        disabled={accessActionLoading !== null}
                        className="rounded-lg bg-amber-600 px-3 py-2 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                      >
                        {accessActionLoading === "restrict" ? "Restricting..." : "Restrict Access"}
                      </button>
                    ) : (
                      <button
                        onClick={() => setOpenConfirm(true)}
                        disabled={accessActionLoading !== null}
                        className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      >
                        {accessActionLoading === "open" ? "Opening..." : "Open to All"}
                      </button>
                    )}
                  </div>
                </div>

                {/* Open to All confirmation */}
                {openConfirm && (
                  <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-4">
                    <p className="text-sm text-yellow-800">
                      This will remove all access restrictions. All team members will be able to see this client.
                    </p>
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={handleOpenAccess}
                        className="rounded-lg bg-yellow-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-yellow-700"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setOpenConfirm(false)}
                        className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Feedback */}
                {accessFeedback && (
                  <div
                    className={`rounded-xl border px-5 py-3 text-sm font-medium ${
                      accessFeedback.type === "success"
                        ? "border-green-200 bg-green-50 text-green-700"
                        : "border-red-200 bg-red-50 text-red-700"
                    }`}
                  >
                    {accessFeedback.message}
                  </div>
                )}

                {/* Loading */}
                {accessLoading && (
                  <div className="flex justify-center py-8">
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                  </div>
                )}

                {/* Member access table (restricted mode) */}
                {!accessLoading && accessSummary?.mode === "restricted" && (
                  <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
                    <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
                      <p className="text-xs font-medium text-gray-500">
                        {accessSummary.records.length} member{accessSummary.records.length !== 1 ? "s" : ""} assigned
                      </p>
                      {unassignedMembers.length > 0 && (
                        <button
                          onClick={() => setShowAddAccess(!showAddAccess)}
                          className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                        >
                          Add Member
                        </button>
                      )}
                    </div>

                    {/* Quick-assign dropdown */}
                    {showAddAccess && unassignedMembers.length > 0 && (
                      <div className="border-b border-gray-100 bg-gray-50 px-5 py-3">
                        <p className="text-xs font-medium text-gray-700 mb-2">Grant access to:</p>
                        <div className="space-y-1.5">
                          {unassignedMembers.map((m) => (
                            <div
                              key={m.user_id}
                              className="flex items-center justify-between rounded-lg bg-white px-3 py-2 border border-gray-100"
                            >
                              <div>
                                <p className="text-sm font-medium text-gray-900">
                                  {m.user_name || m.user_email || m.user_id}
                                </p>
                                {m.user_email && m.user_name && (
                                  <p className="text-xs text-gray-400">{m.user_email}</p>
                                )}
                              </div>
                              <button
                                onClick={() => handleGrantAccess(m.user_id)}
                                disabled={accessActionLoading === m.user_id}
                                className="rounded-md bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                              >
                                {accessActionLoading === m.user_id ? "Adding..." : "Grant Full Access"}
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-gray-400">
                            <th className="px-5 py-3">Member</th>
                            <th className="px-5 py-3">Email</th>
                            <th className="px-5 py-3">Access Level</th>
                            <th className="px-5 py-3">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {accessSummary.records.map((rec) => (
                            <tr key={rec.user_id} className="border-b border-gray-50">
                              <td className="px-5 py-3">
                                <p className="font-medium text-gray-900">
                                  {rec.user_name || rec.user_id}
                                </p>
                              </td>
                              <td className="px-5 py-3 text-xs text-gray-500">
                                {rec.user_email || "\u2014"}
                              </td>
                              <td className="px-5 py-3">
                                <select
                                  value={rec.access_level}
                                  onChange={(e) => handleChangeAccessLevel(rec.user_id, e.target.value)}
                                  disabled={accessActionLoading === rec.user_id}
                                  className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-50"
                                >
                                  <option value="full">Full</option>
                                  <option value="readonly">Read-Only</option>
                                  <option value="none">No Access</option>
                                </select>
                              </td>
                              <td className="px-5 py-3">
                                <button
                                  onClick={() => handleRevokeAccess(rec.user_id)}
                                  disabled={accessActionLoading === rec.user_id}
                                  className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                                >
                                  {accessActionLoading === rec.user_id ? "..." : "Revoke"}
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Open mode placeholder */}
                {!accessLoading && accessSummary?.mode === "open" && (
                  <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
                    <TeamAccessOpenIcon />
                    <p className="mt-3 text-sm text-gray-500">
                      All team members can view and interact with this client.
                    </p>
                    <p className="mt-1 text-xs text-gray-400">
                      Click &quot;Restrict Access&quot; to control which members can access this client.
                    </p>
                  </div>
                )}
              </div>
            )}
          </main>
        </>
      )}

      {/* ── Brief error banner ─────────────────────────────────────────────── */}
      {briefError && (
        <div className="fixed bottom-4 right-4 z-50 max-w-sm rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-lg">
          <div className="flex items-center justify-between gap-2">
            <span>{briefError}</span>
            <button onClick={() => setBriefError(null)} className="text-red-400 hover:text-red-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* ── Brief slide-over panel ─────────────────────────────────────────── */}
      {showBriefPanel && brief && (
        <BriefPanel brief={brief} onClose={() => setShowBriefPanel(false)} />
      )}

      {/* ── Delete confirmation modal ─────────────────────────────────────── */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">Delete client?</h2>
            <p className="mt-2 text-sm text-gray-600">
              This will permanently delete{" "}
              <strong>{client?.name}</strong> and all associated documents and
              interactions. This cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
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
    </>
  );
}

// ─── Suspense wrapper (required for useSearchParams in Next.js App Router) ─────

export default function ClientDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      }
    >
      <ClientDetailContent />
    </Suspense>
  );
}

// ─── Shared sub-components ────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500";

const TYPE_COLOR_CLASSES: Record<string, string> = {
  blue: "bg-blue-100 text-blue-700",
  green: "bg-green-100 text-green-700",
  purple: "bg-purple-100 text-purple-700",
  red: "bg-red-100 text-red-700",
  gray: "bg-gray-100 text-gray-700",
};

function ClientTypeBadge({ type }: { type: { name: string; color: string; description: string } }) {
  return (
    <span
      title={type.description}
      className={`rounded px-2 py-0.5 text-xs font-medium cursor-default ${
        TYPE_COLOR_CLASSES[type.color] ?? "bg-gray-100 text-gray-700"
      }`}
    >
      {type.name}
    </span>
  );
}

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
      <dt className="w-28 shrink-0 pt-0.5 text-xs font-semibold uppercase tracking-wider text-gray-400">
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
    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
  );
}

function CompareSpinner() {
  return (
    <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
  );
}

function BriefSpinner() {
  return (
    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
  );
}

function BriefIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

// ─── Date helpers (for overview cards) ───────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function isOverdue(iso: string): boolean {
  return new Date(iso) < new Date(new Date().toDateString());
}

// ─── Overview card icons ──────────────────────────────────────────────────────

function OverviewDocIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function OverviewChecklistIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

function OverviewCalendarIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function OverviewChatIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}

function TeamAccessOpenIcon() {
  return (
    <svg className="mx-auto h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
    </svg>
  );
}
