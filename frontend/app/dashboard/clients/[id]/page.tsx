"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ChangeEvent, FormEvent, Suspense, useEffect, useState } from "react";

import {
  Client,
  ClientAccessSummary,
  ClientBrief,
  ClientType,
  ClientEngagement,
  ClientUpdateData,
  CompareResponse,
  ComparisonType,
  Document,
  EngagementTemplate,
  OrgMember,
  ProfileFlags,
  createActionItemsApi,
  createBriefsApi,
  createClientTypesApi,
  createClientsApi,
  createConsentApi,
  createDocumentsApi,
  createEngagementsApi,
  createOrganizationsApi,
  createRagApi,
  createStrategiesApi,
  createCommunicationsApi,
  createSessionsApi,
  ChatSessionSummary,
  ChatSessionDetail,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import ActionItemList from "@/components/action-items/ActionItemList";
import SendEmailModal from "@/components/communications/SendEmailModal";
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
import JournalFeed from "@/components/journal/JournalFeed";
import HelpTooltip from "@/components/ui/HelpTooltip";

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

type TabId = "overview" | "documents" | "actions" | "chat" | "conversations" | "timeline" | "strategies" | "journal" | "access";

const BASE_TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "documents", label: "Documents" },
  { id: "actions", label: "Actions" },
  { id: "strategies", label: "Tax Strategies" },
  { id: "journal", label: "Journal" },
  { id: "chat", label: "Chat" },
  { id: "conversations", label: "Conversations" },
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

  // ── Email modal state ───────────────────────────────────────────────────────
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [lastContacted, setLastContacted] = useState<string | null | undefined>(undefined);

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
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);

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

  // ── Engagement state ────────────────────────────────────────────────────────
  const [clientEngagements, setClientEngagements] = useState<ClientEngagement[]>([]);
  const [engagementTemplates, setEngagementTemplates] = useState<EngagementTemplate[]>([]);
  const [engDropdownOpen, setEngDropdownOpen] = useState(false);
  const [engAssigning, setEngAssigning] = useState(false);

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

    // Overview: last contacted date
    createCommunicationsApi(getToken)
      .getLastCommunication(id)
      .then((comm) => setLastContacted(comm?.sent_at ?? null))
      .catch(() => setLastContacted(null));

    // Engagements: client assignments + available templates
    const engApi = createEngagementsApi(getToken);
    engApi.listClientEngagements(id)
      .then(setClientEngagements)
      .catch(() => {/* non-fatal */});
    engApi.listTemplates()
      .then(setEngagementTemplates)
      .catch(() => {/* non-fatal */});
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

  // ── Engagement handlers ──────────────────────────────────────────────────────

  // Templates available for this client (not yet assigned, matching entity type)
  const assignedTemplateIds = new Set(clientEngagements.map((e) => e.template.id));
  const availableTemplates = engagementTemplates.filter((t) => {
    if (assignedTemplateIds.has(t.id)) return false;
    if (!t.entity_types || t.entity_types.length === 0) return true;
    const clientEntity = client?.entity_type?.toLowerCase() ?? "";
    return t.entity_types.some((et) => clientEntity.includes(et.toLowerCase()));
  });

  async function handleAssignEngagement(templateId: string) {
    setEngAssigning(true);
    try {
      const eng = await createEngagementsApi(getToken).assignEngagement(id, { template_id: templateId });
      setClientEngagements((prev) => [...prev, eng]);
      setEngDropdownOpen(false);
    } catch {
      /* non-fatal */
    } finally {
      setEngAssigning(false);
    }
  }

  async function handleRemoveEngagement(engagementId: string) {
    try {
      await createEngagementsApi(getToken).removeEngagement(id, engagementId);
      setClientEngagements((prev) => prev.filter((e) => e.id !== engagementId));
    } catch {
      /* non-fatal */
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

            {/* ── Preparer Relationship ─────────────────────────────────────── */}
            <PreparerRelationshipField
              client={client}
              getToken={getToken}
              onStatusChanged={(updated) => setClient(updated)}
            />

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
            {/* Breadcrumb */}
            <div className="px-8 pt-4 pb-0">
              <nav className="flex items-center gap-1.5 text-sm">
                <Link href="/dashboard/clients" className="text-gray-500 hover:text-gray-700 transition-colors">Clients</Link>
                <span className="text-gray-300">&gt;</span>
                <span className="text-gray-600">{client.name}</span>
              </nav>
            </div>
            <div className="px-8 py-5 flex items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                {/* Client monogram */}
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gray-100 text-lg font-semibold text-gray-600">
                  {client.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <h1 className="text-[28px] font-bold leading-tight text-gray-900">
                      {client.name}
                    </h1>
                    {client.client_type && <ClientTypeBadge type={client.client_type} />}
                  </div>
                  {client.business_name && (
                    <p className="mt-0.5 text-sm text-gray-500">{client.business_name}</p>
                  )}
                  <p className="mt-1 text-sm text-gray-400">
                    {docsLoading ? "…" : `${documents.length} document${documents.length !== 1 ? "s" : ""}`}
                    {" · "}
                    {pendingActionsCount === null ? "…" : `${pendingActionsCount} pending action${pendingActionsCount !== 1 ? "s" : ""}`}
                    {" · "}
                    Last active {formatHeaderDate(client.updated_at)}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => setShowEmailModal(true)}
                  disabled={!client.email}
                  title={!client.email ? "Add a client email address to send emails" : `Email ${client.name}`}
                  className="inline-flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                  </svg>
                  Email
                </button>
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

          {/* ── Engagement badges ──────────────────────────────────────────── */}
          <div className="border-b border-gray-100 bg-gray-50/50 px-8 py-2.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wide mr-1">Engagements</span>
              {clientEngagements.length === 0 && (
                <span className="text-xs text-gray-400 italic">
                  No engagement template assigned. Assign one to auto-generate recurring tasks.
                </span>
              )}
              {clientEngagements.map((eng) => (
                <span
                  key={eng.id}
                  className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 border border-indigo-200 pl-2.5 pr-1 py-0.5 text-xs font-medium text-indigo-700"
                >
                  {eng.template.name}
                  <button
                    onClick={() => handleRemoveEngagement(eng.id)}
                    className="rounded-full p-0.5 text-indigo-400 transition-colors hover:bg-indigo-100 hover:text-indigo-600"
                    title={`Remove ${eng.template.name}`}
                  >
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
              <div className="relative">
                <button
                  onClick={() => setEngDropdownOpen(!engDropdownOpen)}
                  disabled={engAssigning || availableTemplates.length === 0}
                  className="inline-flex items-center gap-1 rounded-full border border-dashed border-gray-300 px-2.5 py-0.5 text-xs font-medium text-gray-500 transition-colors hover:border-gray-400 hover:text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                  </svg>
                  Add
                </button>
                {engDropdownOpen && (
                  <>
                    <div className="fixed inset-0 z-20" onClick={() => setEngDropdownOpen(false)} />
                    <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                      {availableTemplates.map((t) => (
                        <button
                          key={t.id}
                          onClick={() => handleAssignEngagement(t.id)}
                          className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm text-gray-700 transition-colors hover:bg-gray-50"
                        >
                          <div className="min-w-0">
                            <p className="font-medium truncate">{t.name}</p>
                            {t.description && (
                              <p className="text-xs text-gray-400 truncate">{t.description}</p>
                            )}
                          </div>
                        </button>
                      ))}
                      {availableTemplates.length === 0 && (
                        <p className="px-3 py-2 text-xs text-gray-400">All templates assigned</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

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
                    <DetailRow
                      label="Last Contacted"
                      value={
                        lastContacted === undefined
                          ? "..."
                          : lastContacted
                          ? formatRelativeTime(lastContacted)
                          : "No emails sent yet"
                      }
                    />
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
                    <span className="flex items-center gap-1 text-xs text-gray-400">
                      Select 2+ to compare
                      <HelpTooltip content="Select two or more documents to compare side-by-side. The AI highlights key differences, changes, and notable findings." position="left" maxWidth={240} />
                    </span>
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
                      <option value="amendment">Amendment Changes</option>
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
                <StrategyChecklist clientId={id} clientName={client?.name} profileFlags={profileFlags} onFlagsChange={setProfileFlags} />
              </div>
            )}

            {/* ── Journal ───────────────────────────────────────────────── */}
            {activeTab === "journal" && (
              <JournalFeed clientId={id} />
            )}

            {/* ── Chat ──────────────────────────────────────────────────── */}
            {activeTab === "chat" && (
              <div>
                <h2 className="mb-4 text-base font-semibold text-gray-900">Ask AI</h2>
                <ClientChat clientId={id} documentCount={documents.length} />
              </div>
            )}

            {/* ── Conversations ─────────────────────────────────────────── */}
            {activeTab === "conversations" && (
              <ConversationsTab clientId={id} getToken={getToken} />
            )}

            {/* ── Timeline ──────────────────────────────────────────────── */}
            {activeTab === "timeline" && (
              <div className="space-y-8">
                <CalendarView clientId={id} refreshKey={actionItemsRefreshKey} />
                <Timeline
                  clientId={id}
                  refreshKey={actionItemsRefreshKey + timelineRefreshKey}
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

      {/* ── Send email slide-over ──────────────────────────────────────────── */}
      {showEmailModal && client && (
        <SendEmailModal
          clientId={id}
          clientName={client.name}
          clientEmail={client.email}
          onClose={() => setShowEmailModal(false)}
          onSent={() => {
            setTimelineRefreshKey((k) => k + 1);
            createCommunicationsApi(getToken)
              .getLastCommunication(id)
              .then((comm) => setLastContacted(comm?.sent_at ?? null))
              .catch(() => {});
          }}
        />
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

function formatHeaderDate(iso: string): string {
  const date = new Date(iso);
  const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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

// ─── Preparer Relationship Field ─────────────────────────────────────────────

function PreparerRelationshipField({
  client,
  getToken,
  onStatusChanged,
}: {
  client: Client;
  getToken: () => Promise<string | null>;
  onStatusChanged: (updated: Client) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [confirmChange, setConfirmChange] = useState<boolean | null>(null);

  const current = client.is_tax_preparer;

  async function handleChange(isPreparer: boolean) {
    // If switching with tax docs, show confirmation first
    if (client.has_tax_documents && current !== null && isPreparer !== current) {
      setConfirmChange(isPreparer);
      return;
    }
    await doChange(isPreparer);
  }

  async function doChange(isPreparer: boolean) {
    setSaving(true);
    setConfirmChange(null);
    try {
      const consentApi = createConsentApi(getToken);
      await consentApi.setPreparerStatus(client.id, isPreparer);
      // Refetch the client to get updated fields
      const updated = await createClientsApi(getToken).get(client.id);
      onStatusChanged(updated);
    } catch {
      // non-fatal
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border-t border-gray-100 pt-4">
      <Field label="Preparer Relationship">
        {current === null && (
          <p className="mb-2 text-xs text-gray-500">
            Not yet determined — this will be set when you first upload tax
            documents, or you can set it here.
          </p>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            disabled={saving}
            onClick={() => handleChange(true)}
            className={[
              "flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
              current === true
                ? "border-amber-300 bg-amber-50 text-amber-800"
                : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50",
              saving ? "opacity-50" : "",
            ].join(" ")}
          >
            I prepare this client&apos;s returns
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => handleChange(false)}
            className={[
              "flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
              current === false
                ? "border-teal-300 bg-teal-50 text-teal-800"
                : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50",
              saving ? "opacity-50" : "",
            ].join(" ")}
          >
            Advisory or consulting only
          </button>
        </div>

        {/* Confirmation: switching advisory → preparer */}
        {confirmChange === true && (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
            <p className="text-sm text-amber-800">
              Changing to preparer status will require IRC Section 7216 consent
              for the tax documents already uploaded for this client. You&apos;ll
              need to obtain taxpayer consent before continuing AI analysis.
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => doChange(true)}
                disabled={saving}
                className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Confirm Change"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmChange(null)}
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Confirmation: switching preparer → advisory */}
        {confirmChange === false && (
          <div className="mt-3 rounded-md border border-teal-200 bg-teal-50 p-3">
            <p className="text-sm text-teal-800">
              This will switch from Section 7216 requirements to standard AICPA
              confidentiality standards. Are you sure this is an advisory-only
              engagement?
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => doChange(false)}
                disabled={saving}
                className="rounded-md bg-teal-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-700 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Confirm Change"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmChange(null)}
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </Field>
    </div>
  );
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

function ConversationsTab({
  clientId,
  getToken,
}: {
  clientId: string;
  getToken: () => Promise<string | null>;
}) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const perPage = 15;
  const api = createSessionsApi(getToken);

  async function loadPage(p: number) {
    setLoading(true);
    try {
      const res = await api.getClientSessions(clientId, p, perPage);
      setSessions(res.sessions);
      setTotal(res.total);
      setPage(p);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  async function toggleDetail(sessionId: string) {
    if (expandedId === sessionId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(sessionId);
    setDetailLoading(true);
    try {
      const d = await api.getSessionDetail(clientId, sessionId);
      setDetail(d);
    } catch (err) {
      console.error("Failed to load session:", err);
    } finally {
      setDetailLoading(false);
    }
  }

  function fmtDate(d: string) {
    return new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  const totalPages = Math.ceil(total / perPage);

  if (loading && sessions.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent mr-2" />
        Loading conversations...
      </div>
    );
  }

  if (!loading && sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
          <svg className="h-6 w-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <p className="text-sm font-medium text-gray-700">No conversations yet</p>
        <p className="mt-1 max-w-xs text-xs text-gray-400">
          Start chatting with the AI about this client to build conversation history.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-900">Conversations</h2>
        <span className="text-xs text-gray-400">{total} total</span>
      </div>

      <div className="space-y-2">
        {sessions.map((s) => (
          <div
            key={s.id}
            className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden"
          >
            <button
              onClick={() => toggleDetail(s.id)}
              className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {s.title || "Untitled conversation"}
                </p>
                {s.summary && (
                  <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">
                    {s.summary}
                  </p>
                )}
                <div className="mt-1.5 flex items-center gap-2 text-[11px] text-gray-400">
                  <span>{fmtDate(s.started_at)}</span>
                  <span>·</span>
                  <span>{s.message_count} message{s.message_count !== 1 ? "s" : ""}</span>
                </div>
                {s.key_topics && s.key_topics.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {s.key_topics.map((topic, i) => (
                      <span
                        key={i}
                        className="rounded-full bg-blue-50 border border-blue-100 px-2 py-0.5 text-[10px] text-blue-600"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                )}
                {s.key_decisions && s.key_decisions.length > 0 && (
                  <div className="mt-1 space-y-0.5">
                    {s.key_decisions.map((d, i) => (
                      <p key={i} className="text-[11px] text-green-600 flex items-center gap-1">
                        <svg className="h-3 w-3 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                        {d}
                      </p>
                    ))}
                  </div>
                )}
              </div>
              <svg
                className={`h-4 w-4 flex-shrink-0 text-gray-400 mt-1 transition-transform ${
                  expandedId === s.id ? "rotate-180" : ""
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Expanded transcript */}
            {expandedId === s.id && (
              <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 max-h-96 overflow-y-auto">
                {detailLoading ? (
                  <div className="flex items-center justify-center py-4 text-xs text-gray-400">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent mr-1.5" />
                    Loading transcript...
                  </div>
                ) : detail && detail.messages.length > 0 ? (
                  <div className="space-y-3">
                    {detail.messages.map((msg) => (
                      <div key={msg.id} className="flex items-start gap-2">
                        <div
                          className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-bold mt-0.5 ${
                            msg.role === "user"
                              ? "bg-blue-100 text-blue-600"
                              : "bg-gray-200 text-gray-600"
                          }`}
                        >
                          {msg.role === "user" ? "U" : "AI"}
                        </div>
                        <div className="text-xs text-gray-600 leading-relaxed min-w-0">
                          {msg.content}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 text-center py-3">
                    No messages in this session
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            onClick={() => loadPage(page - 1)}
            disabled={page <= 1 || loading}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            Previous
          </button>
          <span className="text-xs text-gray-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => loadPage(page + 1)}
            disabled={page >= totalPages || loading}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function TeamAccessOpenIcon() {
  return (
    <svg className="mx-auto h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
    </svg>
  );
}
