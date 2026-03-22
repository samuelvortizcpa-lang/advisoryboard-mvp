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

  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
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
  model_used: string;
  query_type: string;
  quota_remaining: number | null;
  quota_warning: string | null;
}

export interface SubscriptionInfo {
  tier: string;
  strategic_queries_limit: number;
  strategic_queries_used: number;
  strategic_queries_remaining: number;
  billing_period_start: string | null;
  billing_period_end: string | null;
  max_clients: number | null;
  current_clients: number;
  max_documents: number | null;
  current_documents: number;
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

    chat(clientId: string, question: string, modelOverride?: string | null) {
      return apiFetch<ChatApiResponse>(getToken, `/clients/${clientId}/rag/chat`, {
        method: "POST",
        body: JSON.stringify({ question, model_override: modelOverride ?? null }),
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

// ─── Usage types ───────────────────────────────────────────────────────────────

export interface UsageModelBreakdown {
  model: string;
  queries: number;
  tokens: number;
  cost: number;
}

export interface UsageTypeBreakdown {
  query_type: string;
  queries: number;
  tokens: number;
  cost: number;
}

export interface UsageSummary {
  days: number;
  total_queries: number;
  total_tokens: number;
  total_cost: number;
  breakdown_by_model: UsageModelBreakdown[];
  breakdown_by_query_type: UsageTypeBreakdown[];
}

// ─── Usage analytics types ──────────────────────────────────────────────────────

export interface UsageHistoryItem {
  id: string;
  created_at: string;
  endpoint: string | null;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  client_id: string | null;
  client_name: string | null;
}

export interface UsageHistoryResponse {
  items: UsageHistoryItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface DailyModelStats {
  queries: number;
  tokens: number;
  cost: number;
}

export interface DailyUsageItem {
  date: string;
  total_queries: number;
  total_tokens: number;
  total_cost: number;
  by_model: Record<string, DailyModelStats>;
}

export interface ClientUsageItem {
  client_id: string;
  client_name: string;
  total_queries: number;
  total_tokens: number;
  total_cost: number;
  last_query_at: string;
}

// ─── Usage API factory ─────────────────────────────────────────────────────────

export function createUsageApi(getToken: GetToken) {
  return {
    summary(days = 30) {
      return apiFetch<UsageSummary>(getToken, `/usage/summary?days=${days}`);
    },

    subscription() {
      return apiFetch<SubscriptionInfo>(getToken, `/usage/subscription`);
    },

    history(params: {
      page?: number;
      per_page?: number;
      start_date?: string;
      end_date?: string;
      model?: string;
      endpoint?: string;
      client_id?: string;
    } = {}) {
      const q = new URLSearchParams();
      if (params.page) q.set("page", String(params.page));
      if (params.per_page) q.set("per_page", String(params.per_page));
      if (params.start_date) q.set("start_date", params.start_date);
      if (params.end_date) q.set("end_date", params.end_date);
      if (params.model) q.set("model", params.model);
      if (params.endpoint) q.set("endpoint", params.endpoint);
      if (params.client_id) q.set("client_id", params.client_id);
      const qs = q.toString();
      return apiFetch<UsageHistoryResponse>(getToken, `/usage/history${qs ? `?${qs}` : ""}`);
    },

    daily(days = 30) {
      return apiFetch<DailyUsageItem[]>(getToken, `/usage/daily?days=${days}`);
    },

    byClient(days = 30) {
      return apiFetch<ClientUsageItem[]>(getToken, `/usage/by-client?days=${days}`);
    },

    async exportCsv(startDate?: string, endDate?: string): Promise<void> {
      const token = await getToken();
      const q = new URLSearchParams();
      if (startDate) q.set("start_date", startDate);
      if (endDate) q.set("end_date", endDate);
      const qs = q.toString();
      const res = await fetch(
        `${API_BASE}/usage/export${qs ? `?${qs}` : ""}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "usage_export.csv";
      a.click();
      URL.revokeObjectURL(url);
    },
  };
}

// ─── Admin subscription types ────────────────────────────────────────────────

export interface AdminSubscription {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  tier: string;
  strategic_queries_limit: number;
  strategic_queries_used: number;
  billing_period_start: string;
  billing_period_end: string | null;
  created_at: string;
  updated_at: string;
  usage_percentage: number;
}

export interface AdminSubscriptionSummary {
  total_users: number;
  by_tier: Record<string, number>;
  users_near_limit: number;
  users_over_limit: number;
}

// ─── Admin dashboard types ──────────────────────────────────────────────────

export interface AdminUser {
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  tier: string;
  stripe_status: string | null;
  payment_status: string | null;
  created_at: string;
  client_count: number;
  document_count: number;
  total_queries: number;
  total_cost: number;
  last_active_at: string | null;
  days_since_active: number | null;
  queries_last_7_days: number;
  storage_used_mb: number;
}

export interface AdminOverview {
  total_users: number;
  total_users_by_tier: Record<string, number>;
  active_last_7_days: number;
  active_last_30_days: number;
  total_revenue_mtd: number;
  total_documents: number;
  total_queries_today: number;
  mrr: number;
}

// ─── Admin API factory ──────────────────────────────────────────────────────

export function createAdminApi(getToken: GetToken) {
  return {
    users() {
      return apiFetch<AdminUser[]>(getToken, "/admin/users");
    },

    overview() {
      return apiFetch<AdminOverview>(getToken, "/admin/overview");
    },

    listSubscriptions() {
      return apiFetch<AdminSubscription[]>(getToken, "/admin/subscriptions");
    },

    subscriptionSummary() {
      return apiFetch<AdminSubscriptionSummary>(getToken, "/admin/subscriptions/summary");
    },

    updateTier(userId: string, tier: string) {
      return apiFetch<AdminSubscription>(getToken, `/admin/subscriptions/${userId}`, {
        method: "PUT",
        body: JSON.stringify({ tier }),
      });
    },

    resetUsage(userId: string) {
      return apiFetch<AdminSubscription>(getToken, `/admin/subscriptions/${userId}/reset-usage`, {
        method: "POST",
      });
    },
  };
}

// ─── Stripe types ────────────────────────────────────────────────────────────

export interface StripeStatus {
  stripe_status: string;
  stripe_customer_id: string | null;
  tier: string;
}

// ─── Stripe API factory ─────────────────────────────────────────────────────

export function createStripeApi(getToken: GetToken) {
  return {
    createCheckout(tier: string, billingInterval: "monthly" | "annual" = "monthly") {
      return apiFetch<{ url: string }>(getToken, "/stripe/create-checkout", {
        method: "POST",
        body: JSON.stringify({ tier, billing_interval: billingInterval }),
      });
    },

    createPortal() {
      return apiFetch<{ url: string }>(getToken, "/stripe/create-portal", {
        method: "POST",
      });
    },

    status() {
      return apiFetch<StripeStatus>(getToken, "/stripe/status");
    },
  };
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

// ─── Consent types (IRC §7216) ───────────────────────────────────────────────

export interface ConsentRecord {
  id: string;
  client_id: string;
  user_id: string;
  consent_type: string;
  status: string;
  consent_date: string | null;
  expiration_date: string | null;
  consent_method: string | null;
  taxpayer_name: string | null;
  preparer_name: string | null;
  preparer_firm: string | null;
  notes: string | null;
  form_generated_at: string | null;
  signing_token: string | null;
  sent_to_email: string | null;
  sent_at: string | null;
  signed_at: string | null;
  signer_typed_name: string | null;
  signed_pdf_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConsentStatus {
  consent_status: string;
  has_tax_documents: boolean;
  latest_consent: ConsentRecord | null;
  is_expired: boolean;
  days_until_expiry: number | null;
}

export interface ConsentCreateRequest {
  consent_type: string;
  status: string;
  consent_date?: string | null;
  expiration_date?: string | null;
  consent_method?: string | null;
  taxpayer_name?: string | null;
  preparer_name?: string | null;
  preparer_firm?: string | null;
  notes?: string | null;
}

// ─── Consent API factory ────────────────────────────────────────────────────

export function createConsentApi(getToken: GetToken) {
  return {
    getStatus(clientId: string) {
      return apiFetch<ConsentStatus>(getToken, `/clients/${clientId}/consent`);
    },

    create(clientId: string, data: ConsentCreateRequest) {
      return apiFetch<ConsentRecord>(getToken, `/clients/${clientId}/consent`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    async downloadForm(clientId: string): Promise<void> {
      const token = await getToken();
      const res = await fetch(
        `${API_BASE}/clients/${clientId}/consent/generate-form`,
        {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      );
      if (!res.ok) {
        throw new Error(`PDF generation failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.download = match ? match[1] : "7216_consent_form.pdf";
      a.click();
      URL.revokeObjectURL(url);
    },

    history(clientId: string) {
      return apiFetch<ConsentRecord[]>(
        getToken,
        `/clients/${clientId}/consent/history`
      );
    },

    sendForSignature(
      clientId: string,
      data: { taxpayer_email: string; taxpayer_name: string; preparer_name: string; preparer_firm?: string }
    ) {
      return apiFetch<{ success: boolean; consent_id: string; message: string }>(
        getToken,
        `/clients/${clientId}/consent/send-for-signature`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      );
    },
  };
}

// ─── Alert types ───────────────────────────────────────────────────────────────

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertType = "overdue_action" | "upcoming_deadline" | "stale_client" | "stuck_document" | "consent_needed" | "consent_expiring";

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

export interface ZoomRule {
  id: string;
  user_id: string;
  match_field: string;
  match_value: string;
  client_id: string;
  client_name: string;
  is_active: boolean;
  created_at: string;
}

export interface ZoomRuleCreateData {
  match_field: string;
  match_value: string;
  client_id: string;
}

export interface UnmatchedRecording {
  document_id: string;
  filename: string;
  file_size: number;
  source: string;
  external_id: string | null;
  upload_date: string;
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

    getMicrosoftAuthUrl() {
      return apiFetch<{ authorization_url: string }>(
        getToken,
        "/integrations/microsoft/authorize"
      );
    },

    getZoomAuthUrl() {
      return apiFetch<{ authorization_url: string }>(
        getToken,
        "/integrations/zoom/authorize"
      );
    },

    getFrontAuthUrl() {
      return apiFetch<{ authorization_url: string }>(
        getToken,
        "/integrations/front/authorize"
      );
    },

    connectFrontToken(apiToken: string) {
      return apiFetch<IntegrationConnection>(
        getToken,
        "/integrations/front/connect-token",
        {
          method: "POST",
          body: JSON.stringify({ api_token: apiToken }),
        }
      );
    },

    connectFathom(apiKey: string) {
      return apiFetch<IntegrationConnection>(
        getToken,
        "/integrations/fathom/connect",
        {
          method: "POST",
          body: JSON.stringify({ api_key: apiKey }),
        }
      );
    },

    importFathomTranscript(file: File, clientId: string) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("client_id", clientId);
      return apiFetch<{ status: string; document_id: string }>(
        getToken,
        "/integrations/fathom/import",
        {
          method: "POST",
          body: formData,
        }
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

    // ── Zoom rules ──
    listZoomRules() {
      return apiFetch<ZoomRule[]>(getToken, "/integrations/zoom-rules");
    },

    createZoomRule(data: ZoomRuleCreateData) {
      return apiFetch<ZoomRule>(getToken, "/integrations/zoom-rules", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    deleteZoomRule(ruleId: string) {
      return apiFetch<void>(getToken, `/integrations/zoom-rules/${ruleId}`, {
        method: "DELETE",
      });
    },

    autoGenerateZoomRules() {
      return apiFetch<ZoomRule[]>(
        getToken,
        "/integrations/zoom-rules/auto-generate",
        { method: "POST" }
      );
    },

    // ── Unmatched recordings ──
    listUnmatchedRecordings() {
      return apiFetch<UnmatchedRecording[]>(
        getToken,
        "/integrations/zoom/unmatched"
      );
    },

    getAutoSyncStatus() {
      return apiFetch<{
        scheduler_running: boolean;
        last_run_at: string | null;
        next_run_at: string | null;
        active_syncs: string[];
        last_run_summary: {
          connections_checked: number;
          connections_synced: number;
          connections_skipped: number;
          connections_failed: number;
        } | null;
      }>(getToken, "/integrations/admin/sync-status");
    },

    assignRecording(documentId: string, clientId: string, createRule?: { match_field: string; match_value: string }) {
      return apiFetch<{ status: string }>(
        getToken,
        "/integrations/zoom/assign",
        {
          method: "POST",
          body: JSON.stringify({
            document_id: documentId,
            client_id: clientId,
            create_rule: createRule,
          }),
        }
      );
    },
  };
}

// ─── Organization types ──────────────────────────────────────────────────────

export interface Organization {
  id: string;
  name: string;
  slug: string;
  org_type: string;
  max_members: number;
  member_count: number;
  role: string | null;
}

export interface OrgMember {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  role: string;
  joined_at: string;
  is_active: boolean;
}

export interface OrgDetail extends Organization {
  owner_user_id: string;
  settings: Record<string, unknown>;
  subscription_tier: string | null;
  client_count: number;
  created_at: string;
  updated_at: string;
}

// ─── Organizations API factory ───────────────────────────────────────────────

export function createOrganizationsApi(getToken: GetToken) {
  return {
    list() {
      return apiFetch<Organization[]>(getToken, "/organizations");
    },

    get(orgId: string) {
      return apiFetch<OrgDetail>(getToken, `/organizations/${orgId}`);
    },

    update(orgId: string, data: { name?: string; settings?: Record<string, unknown> }) {
      return apiFetch<OrgDetail>(getToken, `/organizations/${orgId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    listMembers(orgId: string) {
      return apiFetch<OrgMember[]>(getToken, `/organizations/${orgId}/members`);
    },

    inviteMember(orgId: string, userEmail: string, role: string = "member") {
      return apiFetch<OrgMember>(getToken, `/organizations/${orgId}/members`, {
        method: "POST",
        body: JSON.stringify({ user_email: userEmail, role }),
      });
    },

    updateMemberRole(orgId: string, userId: string, role: string) {
      return apiFetch<OrgMember>(getToken, `/organizations/${orgId}/members/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
    },

    removeMember(orgId: string, userId: string) {
      return apiFetch<void>(getToken, `/organizations/${orgId}/members/${userId}`, {
        method: "DELETE",
      });
    },

    // ── Client access delegation ──

    fetchClientAccess(orgId: string, clientId: string) {
      return apiFetch<ClientAccessSummary>(
        getToken,
        `/organizations/${orgId}/clients/${clientId}/access`
      );
    },

    grantClientAccess(orgId: string, clientId: string, userId: string, accessLevel: string = "full") {
      return apiFetch<ClientAccess>(
        getToken,
        `/organizations/${orgId}/clients/${clientId}/access`,
        {
          method: "POST",
          body: JSON.stringify({ user_id: userId, access_level: accessLevel }),
        }
      );
    },

    revokeClientAccess(orgId: string, clientId: string, userId: string) {
      return apiFetch<void>(
        getToken,
        `/organizations/${orgId}/clients/${clientId}/access/${userId}`,
        { method: "DELETE" }
      );
    },

    restrictClient(orgId: string, clientId: string) {
      return apiFetch<ClientAccessSummary>(
        getToken,
        `/organizations/${orgId}/clients/${clientId}/access/restrict`,
        { method: "POST" }
      );
    },
  };
}

// ─── Client access types ─────────────────────────────────────────────────────

export interface ClientAccess {
  id: string;
  client_id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  access_level: string;
  assigned_by: string | null;
  created_at: string;
}

export interface ClientAccessSummary {
  mode: "open" | "restricted";
  records: ClientAccess[];
}
