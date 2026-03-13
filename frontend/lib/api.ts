// NEXT_PUBLIC_API_URL is baked in at build time; set it in Railway before building.
// Falls back to http://localhost:8000 for local development.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api`;

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ClientType {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  color: string;
  created_at: string;
  updated_at: string;
}

export interface ClientTypeListResponse {
  types: ClientType[];
  total: number;
}

export interface ClientTypeCreateData {
  name: string;
  description: string;
  system_prompt: string;
  color: string;
}

export type ClientTypeUpdateData = Partial<ClientTypeCreateData>;

export interface Client {
  id: string;
  owner_id: string;
  name: string;
  email: string | null;
  business_name: string | null;
  entity_type: string | null;
  industry: string | null;
  notes: string | null;
  client_type_id: string | null;
  custom_instructions: string | null;
  client_type: ClientType | null;
  created_at: string;
  updated_at: string;
}

export interface ClientListResponse {
  items: Client[];
  total: number;
  skip: number;
  limit: number;
}

export interface ClientCreateData {
  name: string;
  email?: string;
  business_name?: string;
  entity_type?: string;
  industry?: string;
  notes?: string;
  client_type_id?: string | null;
  custom_instructions?: string | null;
}

export type ClientUpdateData = Partial<ClientCreateData>;

// ─── Core fetch helper ────────────────────────────────────────────────────────

type GetToken = () => Promise<string | null>;

async function apiFetch<T>(
  getToken: GetToken,
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getToken();

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }

  // 204 No Content — nothing to parse
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Document types ───────────────────────────────────────────────────────────

export interface Document {
  id: string;
  client_id: string;
  uploaded_by: string | null;
  filename: string;
  file_type: string;
  file_size: number;
  upload_date: string;
  processed: boolean;
  processing_error: string | null;
  document_type: string | null;
  document_subtype: string | null;
  document_period: string | null;
  classification_confidence: number | null;
  is_superseded: boolean;
  superseded_by: string | null;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  skip: number;
  limit: number;
}

// ─── Clients API factory ──────────────────────────────────────────────────────
// Call this inside a component after obtaining getToken from useAuth():
//   const { getToken } = useAuth();
//   const api = createClientsApi(getToken);

export function createClientsApi(getToken: GetToken) {
  return {
    list(skip = 0, limit = 50) {
      return apiFetch<ClientListResponse>(
        getToken,
        `/clients?skip=${skip}&limit=${limit}`
      );
    },

    get(id: string) {
      return apiFetch<Client>(getToken, `/clients/${id}`);
    },

    create(data: ClientCreateData) {
      return apiFetch<Client>(getToken, "/clients", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    update(id: string, data: ClientUpdateData) {
      return apiFetch<Client>(getToken, `/clients/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      });
    },

    delete(id: string) {
      return apiFetch<void>(getToken, `/clients/${id}`, { method: "DELETE" });
    },
  };
}

// ─── Client types API factory ─────────────────────────────────────────────────

export function createClientTypesApi(getToken: GetToken) {
  return {
    list() {
      return apiFetch<ClientTypeListResponse>(getToken, "/client-types");
    },

    create(data: ClientTypeCreateData) {
      return apiFetch<ClientType>(getToken, "/client-types", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    update(id: string, data: ClientTypeUpdateData) {
      return apiFetch<ClientType>(getToken, `/client-types/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    delete(id: string) {
      return apiFetch<void>(getToken, `/client-types/${id}`, { method: "DELETE" });
    },
  };
}

// ─── RAG types ────────────────────────────────────────────────────────────────

export type ComparisonType = "summary" | "changes" | "financial";

export interface CompareDocumentMeta {
  id: string;
  filename: string;
}

export interface CompareResponse {
  comparison_type: ComparisonType;
  documents: CompareDocumentMeta[];
  report: string;
}

export interface RagStatus {
  total_documents: number;
  processed: number;
  pending: number;
  errors: number;
  total_chunks: number;
}

export interface RagSource {
  document_id: string;
  filename: string;
  preview: string;
  score: number;
  chunk_text: string;
  chunk_index: number;
  page_number?: number;
  image_url?: string;
}

export interface ChatApiResponse {
  answer: string;
  confidence_tier: "high" | "medium" | "low";
  confidence_score: number;
  sources: RagSource[];
}

export interface ProcessResponse {
  queued: number;
  message: string;
}

// ─── Chat history types ───────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  client_id: string;
  user_id: string | null;
  role: "user" | "assistant";
  content: string;
  sources: RagSource[] | null;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  total: number;
  skip: number;
  limit: number;
}

// ─── RAG API factory ──────────────────────────────────────────────────────────

export function createRagApi(getToken: GetToken) {
  return {
    status(clientId: string) {
      return apiFetch<RagStatus>(getToken, `/clients/${clientId}/rag/status`);
    },

    processAll(clientId: string) {
      return apiFetch<ProcessResponse>(getToken, `/clients/${clientId}/rag/process`, {
        method: "POST",
      });
    },

    processDocument(clientId: string, documentId: string) {
      return apiFetch<ProcessResponse>(
        getToken,
        `/clients/${clientId}/documents/${documentId}/process`,
        { method: "POST" }
      );
    },

    chat(clientId: string, question: string) {
      return apiFetch<ChatApiResponse>(getToken, `/clients/${clientId}/rag/chat`, {
        method: "POST",
        body: JSON.stringify({ question }),
      });
    },

    getChatHistory(clientId: string, limit = 100, skip = 0) {
      return apiFetch<ChatHistoryResponse>(
        getToken,
        `/clients/${clientId}/chat-history?limit=${limit}&skip=${skip}`
      );
    },

    async exportChat(clientId: string, format: "txt" | "pdf"): Promise<void> {
      const token = await getToken();
      const res = await fetch(
        `${API_BASE}/clients/${clientId}/chat-history/export?format=${format}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) {
        throw new Error(`Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.download = match ? match[1] : `chat-history.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    },

    clearChatHistory(clientId: string) {
      return apiFetch<void>(getToken, `/clients/${clientId}/chat-history`, {
        method: "DELETE",
      });
    },

    compare(clientId: string, documentIds: string[], comparisonType: ComparisonType) {
      return apiFetch<CompareResponse>(getToken, `/clients/${clientId}/rag/compare`, {
        method: "POST",
        body: JSON.stringify({ document_ids: documentIds, comparison_type: comparisonType }),
      });
    },

    backfillPages() {
      return apiFetch<BackfillResponse>(getToken, `/documents/backfill-pages`, {
        method: "POST",
      });
    },
  };
}

export interface BackfillResponse {
  processed: number;
  skipped: number;
  total_pages: number;
  message: string;
}

// ─── Brief types ───────────────────────────────────────────────────────────────

export interface ClientBrief {
  id: string;
  client_id: string;
  content: string;
  generated_at: string;
  document_count: number | null;
  action_item_count: number | null;
  metadata_: Record<string, unknown> | null;
}

// ─── Briefs API factory ────────────────────────────────────────────────────────

export function createBriefsApi(getToken: GetToken) {
  return {
    generate(clientId: string) {
      return apiFetch<ClientBrief>(getToken, `/clients/${clientId}/briefs/generate`, {
        method: "POST",
      });
    },

    getLatest(clientId: string) {
      return apiFetch<ClientBrief | null>(getToken, `/clients/${clientId}/briefs/latest`);
    },
  };
}

// ─── Alert types ───────────────────────────────────────────────────────────────

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertType = "overdue_action" | "upcoming_deadline" | "stale_client" | "stuck_document";

export interface Alert {
  id: string;
  type: AlertType;
  severity: AlertSeverity;
  client_id: string;
  client_name: string;
  message: string;
  related_id: string;
  created_at: string;
}

export interface AlertsListResponse {
  alerts: Alert[];
  total: number;
}

export interface AlertsSummaryResponse {
  critical: number;
  warning: number;
  info: number;
  total: number;
}

// ─── Alerts API factory ────────────────────────────────────────────────────────

export function createAlertsApi(getToken: GetToken) {
  return {
    list() {
      return apiFetch<AlertsListResponse>(getToken, "/alerts");
    },

    summary() {
      return apiFetch<AlertsSummaryResponse>(getToken, "/alerts/summary");
    },

    dismiss(alertType: string, relatedId: string) {
      return apiFetch<{ dismissed: boolean }>(getToken, "/alerts/dismiss", {
        method: "POST",
        body: JSON.stringify({ alert_type: alertType, related_id: relatedId }),
      });
    },
  };
}

// ─── Action item types ────────────────────────────────────────────────────────

export interface ActionItem {
  id: string;
  document_id: string;
  client_id: string;
  text: string;
  status: "pending" | "completed" | "cancelled";
  priority: "low" | "medium" | "high" | null;
  due_date: string | null;
  extracted_at: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  document_filename: string | null;
}

export interface ActionItemListResponse {
  items: ActionItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface ActionItemUpdate {
  status?: "pending" | "completed" | "cancelled";
  priority?: "low" | "medium" | "high" | null;
  due_date?: string | null;
}

// ─── Action items API factory ─────────────────────────────────────────────────

export function createActionItemsApi(getToken: GetToken) {
  return {
    list(clientId: string, statusFilter?: string, skip = 0, limit = 50) {
      const params = new URLSearchParams({
        skip: String(skip),
        limit: String(limit),
      });
      if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
      return apiFetch<ActionItemListResponse>(
        getToken,
        `/clients/${clientId}/action-items?${params}`
      );
    },

    listPending(clientId: string) {
      return apiFetch<ActionItemListResponse>(
        getToken,
        `/clients/${clientId}/action-items/pending`
      );
    },

    update(itemId: string, data: ActionItemUpdate) {
      return apiFetch<ActionItem>(getToken, `/action-items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    delete(itemId: string) {
      return apiFetch<void>(getToken, `/action-items/${itemId}`, {
        method: "DELETE",
      });
    },

    reextract(documentId: string) {
      return apiFetch<{ message: string }>(
        getToken,
        `/documents/${documentId}/reextract-action-items`,
        { method: "POST" }
      );
    },
  };
}

// ─── Documents API factory ────────────────────────────────────────────────────
// Call this inside a component after obtaining getToken from useAuth():
//   const { getToken } = useAuth();
//   const api = createDocumentsApi(getToken);

// ─── Timeline types ───────────────────────────────────────────────────────────

export interface DocumentTimelineItem {
  type: "document";
  id: string;
  date: string;
  filename: string;
  file_type: string;
  file_size: number;
  processed: boolean;
}

export interface ActionItemTimelineItem {
  type: "action_item";
  id: string;
  date: string;
  text: string;
  status: "pending" | "completed" | "cancelled";
  priority: "low" | "medium" | "high" | null;
  source_doc: string | null;
}

export type TimelineItem = DocumentTimelineItem | ActionItemTimelineItem;

export interface TimelineResponse {
  items: TimelineItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface TimelineParams {
  types?: string[];
  start_date?: string;
  end_date?: string;
  limit?: number;
  skip?: number;
}

// ─── Timeline API factory ─────────────────────────────────────────────────────

export function createTimelineApi(getToken: GetToken) {
  return {
    list(clientId: string, params?: TimelineParams) {
      const query = new URLSearchParams();
      params?.types?.forEach((t) => query.append("types", t));
      if (params?.start_date) query.set("start_date", params.start_date);
      if (params?.end_date) query.set("end_date", params.end_date);
      if (params?.limit != null) query.set("limit", String(params.limit));
      if (params?.skip != null) query.set("skip", String(params.skip));
      const qs = query.toString();
      return apiFetch<TimelineResponse>(
        getToken,
        `/clients/${clientId}/timeline${qs ? `?${qs}` : ""}`
      );
    },
  };
}

// ─── Documents API factory ────────────────────────────────────────────────────
// Call this inside a component after obtaining getToken from useAuth():
//   const { getToken } = useAuth();
//   const api = createDocumentsApi(getToken);

export function createDocumentsApi(getToken: GetToken) {
  return {
    list(clientId: string, skip = 0, limit = 50) {
      return apiFetch<DocumentListResponse>(
        getToken,
        `/clients/${clientId}/documents?skip=${skip}&limit=${limit}`
      );
    },

    async upload(clientId: string, file: File): Promise<Document> {
      const token = await getToken();
      const form = new FormData();
      form.append("file", file);

      const res = await fetch(`${API_BASE}/clients/${clientId}/documents`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });

      if (!res.ok) {
        let message = `Upload failed (${res.status})`;
        try {
          const body = await res.json();
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // ignore parse errors
        }
        throw new Error(message);
      }

      return res.json() as Promise<Document>;
    },

    async download(documentId: string, filename: string): Promise<void> {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/documents/${documentId}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!res.ok) {
        throw new Error(`Download failed (${res.status})`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    },

    delete(documentId: string) {
      return apiFetch<void>(getToken, `/documents/${documentId}`, {
        method: "DELETE",
      });
    },
  };
}

// ─── Integration types ─────────────────────────────────────────────────────

export interface IntegrationConnection {
  id: string;
  provider: string;
  provider_email: string | null;
  is_active: boolean;
  scopes: string | null;
  last_sync_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RoutingRule {
  id: string;
  user_id: string;
  email_address: string;
  client_id: string;
  client_name: string;
  match_type: string;
  is_active: boolean;
  created_at: string;
}

export interface SyncLog {
  id: string;
  connection_id: string;
  sync_type: string | null;
  status: string | null;
  emails_found: number;
  emails_ingested: number;
  emails_skipped: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface RoutingRuleCreateData {
  email_address: string;
  client_id: string;
  match_type: string;
}

// ─── Integrations API factory ──────────────────────────────────────────────

export function createIntegrationsApi(getToken: GetToken) {
  return {
    // ── OAuth ──
    getGoogleAuthUrl() {
      return apiFetch<{ authorization_url: string }>(
        getToken,
        "/integrations/google/authorize"
      );
    },

    // ── Connections ──
    listConnections() {
      return apiFetch<IntegrationConnection[]>(
        getToken,
        "/integrations/connections"
      );
    },

    disconnect(connectionId: string) {
      return apiFetch<void>(
        getToken,
        `/integrations/connections/${connectionId}`,
        { method: "DELETE" }
      );
    },

    // ── Sync ──
    triggerSync(connectionId: string, maxResults = 50, sinceHours = 24) {
      return apiFetch<SyncLog>(
        getToken,
        `/integrations/connections/${connectionId}/sync?max_results=${maxResults}&since_hours=${sinceHours}`,
        { method: "POST" }
      );
    },

    triggerDeepSync(connectionId: string) {
      return apiFetch<SyncLog>(
        getToken,
        `/integrations/connections/${connectionId}/sync-all`,
        { method: "POST" }
      );
    },

    getSyncHistory(connectionId: string, limit = 20) {
      return apiFetch<SyncLog[]>(
        getToken,
        `/integrations/connections/${connectionId}/sync-history?limit=${limit}`
      );
    },

    // ── Routing rules ──
    listRoutingRules() {
      return apiFetch<RoutingRule[]>(
        getToken,
        "/integrations/routing-rules"
      );
    },

    createRoutingRule(data: RoutingRuleCreateData) {
      return apiFetch<RoutingRule>(getToken, "/integrations/routing-rules", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    deleteRoutingRule(ruleId: string) {
      return apiFetch<void>(getToken, `/integrations/routing-rules/${ruleId}`, {
        method: "DELETE",
      });
    },

    autoGenerateRules() {
      return apiFetch<RoutingRule[]>(
        getToken,
        "/integrations/routing-rules/auto-generate",
        { method: "POST" }
      );
    },
  };
}
