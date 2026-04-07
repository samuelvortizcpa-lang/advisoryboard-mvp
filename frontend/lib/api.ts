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

export interface AssignedMember {
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  role: string;
}

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
  is_tax_preparer: boolean | null;
  consent_status: string;
  has_tax_documents: boolean;
  data_handling_acknowledged: boolean;
  document_count: number;
  created_at: string;
  updated_at: string;
  assigned_members?: AssignedMember[];
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

export type GetToken = () => Promise<string | null>;

async function apiFetch<T>(
  getToken: GetToken,
  path: string,
  options: RequestInit = {},
  orgId?: string,
): Promise<T> {
  const token = await getToken();

  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(orgId ? { "X-Org-Id": orgId } : {}),
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

/**
 * Like apiFetch but returns a raw Blob instead of parsing JSON.
 * Used for PDF downloads and other binary responses.
 */
async function apiFetchBlob(
  getToken: GetToken,
  path: string,
  options: RequestInit = {},
  orgId?: string,
): Promise<Blob> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(orgId ? { "X-Org-Id": orgId } : {}),
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

  return res.blob();
}

/**
 * Create a bound fetch function that always includes the given orgId.
 * Factory functions use this so callers don't have to thread orgId through
 * every individual method call.
 */
function boundFetch(getToken: GetToken, orgId?: string) {
  return <T>(path: string, options: RequestInit = {}) =>
    apiFetch<T>(getToken, path, options, orgId);
}

function boundFetchBlob(getToken: GetToken, orgId?: string) {
  return (path: string, options: RequestInit = {}) =>
    apiFetchBlob(getToken, path, options, orgId);
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
  amends_subtype: string | null;
  amendment_number: number | null;
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

export function createClientsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list(skip = 0, limit = 50) {
      return f<ClientListResponse>(`/clients?skip=${skip}&limit=${limit}`);
    },

    get(id: string) {
      return f<Client>(`/clients/${id}`);
    },

    create(data: ClientCreateData) {
      return f<Client>("/clients", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    update(id: string, data: ClientUpdateData) {
      return f<Client>(`/clients/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      });
    },

    delete(id: string) {
      return f<void>(`/clients/${id}`, { method: "DELETE" });
    },
  };
}

// ─── Client types API factory ─────────────────────────────────────────────────

export function createClientTypesApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list() {
      return f<ClientTypeListResponse>("/client-types");
    },

    create(data: ClientTypeCreateData) {
      return f<ClientType>("/client-types", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    update(id: string, data: ClientTypeUpdateData) {
      return f<ClientType>(`/client-types/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    delete(id: string) {
      return f<void>(`/client-types/${id}`, { method: "DELETE" });
    },
  };
}

// ─── RAG types ────────────────────────────────────────────────────────────────

export type ComparisonType = "summary" | "changes" | "financial" | "amendment";

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
  seats_included: number;
  seats_addon: number;
  seats_total: number;
  seats_used: number;
}

export interface SeatInfo {
  included: number;
  addon_purchased: number;
  total_allowed: number;
  current_used: number;
  can_add: boolean;
  per_seat_price: number;
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

export function createRagApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    status(clientId: string) {
      return f<RagStatus>(`/clients/${clientId}/rag/status`);
    },

    processAll(clientId: string) {
      return f<ProcessResponse>(`/clients/${clientId}/rag/process`, {
        method: "POST",
      });
    },

    processDocument(clientId: string, documentId: string) {
      return f<ProcessResponse>(
        `/clients/${clientId}/documents/${documentId}/process`,
        { method: "POST" }
      );
    },

    chat(clientId: string, question: string, modelOverride?: string | null) {
      return f<ChatApiResponse>(`/clients/${clientId}/rag/chat`, {
        method: "POST",
        body: JSON.stringify({ question, model_override: modelOverride ?? null }),
      });
    },

    async chatStream(
      clientId: string,
      question: string,
      modelOverride: string | null | undefined,
      onToken: (token: string) => void,
      onDone: (meta: {
        sources: RagSource[];
        confidence_tier: string;
        confidence_score: number;
        model_used: string;
        query_type: string;
        quota_remaining: number | null;
        quota_warning: string | null;
      }) => void,
    ): Promise<void> {
      const token = await getToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      if (orgId) headers["X-Org-Id"] = orgId;

      const res = await fetch(
        `${API_BASE}/clients/${clientId}/rag/chat/stream`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({ question, model_override: modelOverride ?? null }),
        },
      );

      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6);
          try {
            const event = JSON.parse(json);
            if (event.type === "token") {
              onToken(event.content);
            } else if (event.type === "done") {
              onDone(event);
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    },

    getChatHistory(clientId: string, limit = 100, skip = 0) {
      return f<ChatHistoryResponse>(
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
      return f<void>(`/clients/${clientId}/chat-history`, {
        method: "DELETE",
      });
    },

    compare(clientId: string, documentIds: string[], comparisonType: ComparisonType) {
      return f<CompareResponse>(`/clients/${clientId}/rag/compare`, {
        method: "POST",
        body: JSON.stringify({ document_ids: documentIds, comparison_type: comparisonType }),
      });
    },

    backfillPages() {
      return f<BackfillResponse>(`/documents/backfill-pages`, {
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

export function createUsageApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    summary(days = 30) {
      return f<UsageSummary>(`/usage/summary?days=${days}`);
    },

    subscription() {
      return f<SubscriptionInfo>(`/usage/subscription`);
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
      return f<UsageHistoryResponse>(`/usage/history${qs ? `?${qs}` : ""}`);
    },

    daily(days = 30) {
      return f<DailyUsageItem[]>(`/usage/daily?days=${days}`);
    },

    byClient(days = 30) {
      return f<ClientUsageItem[]>(`/usage/by-client?days=${days}`);
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

export function createAdminApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    users() {
      return f<AdminUser[]>("/admin/users");
    },

    overview() {
      return f<AdminOverview>("/admin/overview");
    },

    listSubscriptions() {
      return f<AdminSubscription[]>("/admin/subscriptions");
    },

    subscriptionSummary() {
      return f<AdminSubscriptionSummary>("/admin/subscriptions/summary");
    },

    updateTier(userId: string, tier: string) {
      return f<AdminSubscription>(`/admin/subscriptions/${userId}`, {
        method: "PUT",
        body: JSON.stringify({ tier }),
      });
    },

    resetUsage(userId: string) {
      return f<AdminSubscription>(`/admin/subscriptions/${userId}/reset-usage`, {
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

export function createStripeApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    createCheckout(tier: string, billingInterval: "monthly" | "annual" = "monthly", addonSeats?: number) {
      const body: Record<string, unknown> = { tier, billing_interval: billingInterval };
      if (addonSeats !== undefined && addonSeats > 0 && tier === "firm") {
        body.addon_seats = addonSeats;
      }
      return f<{ url: string }>("/stripe/create-checkout", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },

    createPortal() {
      return f<{ url: string }>("/stripe/create-portal", {
        method: "POST",
      });
    },

    status() {
      return f<StripeStatus>("/stripe/status");
    },

    getSeats() {
      return f<SeatInfo>("/stripe/seats");
    },

    updateSeats(addonSeats: number) {
      return f<SeatInfo>("/stripe/update-seats", {
        method: "POST",
        body: JSON.stringify({ addon_seats: addonSeats }),
      });
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

export function createBriefsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    generate(clientId: string) {
      return f<ClientBrief>(`/clients/${clientId}/briefs/generate`, {
        method: "POST",
      });
    },

    getLatest(clientId: string) {
      return f<ClientBrief | null>(`/clients/${clientId}/briefs/latest`);
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
  is_tax_preparer: boolean | null;
  data_handling_acknowledged: boolean;
  consent_tier: "full_7216" | "aicpa_acknowledgment" | null;
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

export function createConsentApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    getStatus(clientId: string) {
      return f<ConsentStatus>(`/clients/${clientId}/consent`);
    },

    create(clientId: string, data: ConsentCreateRequest) {
      return f<ConsentRecord>(`/clients/${clientId}/consent`, {
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
      return f<ConsentRecord[]>(
        `/clients/${clientId}/consent/history`
      );
    },

    sendForSignature(
      clientId: string,
      data: { taxpayer_email: string; taxpayer_name: string; preparer_name: string; preparer_firm?: string }
    ) {
      return f<{ success: boolean; consent_id: string; message: string }>(
        `/clients/${clientId}/consent/send-for-signature`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      );
    },

    setPreparerStatus(clientId: string, is_tax_preparer: boolean) {
      return f<ConsentStatus>(`/clients/${clientId}/preparer-status`, {
        method: "POST",
        body: JSON.stringify({ is_tax_preparer }),
      });
    },

    recordAdvisoryAcknowledgment(clientId: string) {
      return f<ConsentRecord>(`/clients/${clientId}/advisory-acknowledgment`, {
        method: "POST",
      });
    },
  };
}

// ─── Alert types ───────────────────────────────────────────────────────────────

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertType = "overdue_action" | "upcoming_deadline" | "stale_client" | "stuck_document" | "consent_needed" | "consent_expiring" | "preparer_determination_needed" | "quarterly_estimate_due" | "follow_up_due";

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

export function createAlertsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list() {
      return f<AlertsListResponse>("/alerts");
    },

    summary() {
      return f<AlertsSummaryResponse>("/alerts/summary");
    },

    dismiss(alertType: string, relatedId: string) {
      return f<{ dismissed: boolean }>("/alerts/dismiss", {
        method: "POST",
        body: JSON.stringify({ alert_type: alertType, related_id: relatedId }),
      });
    },
  };
}

// ─── Action item types ────────────────────────────────────────────────────────

export interface ActionItem {
  id: string;
  document_id: string | null;
  client_id: string;
  text: string;
  status: "pending" | "completed" | "cancelled";
  priority: "low" | "medium" | "high" | null;
  due_date: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  notes: string | null;
  source: "ai_extracted" | "manual" | "engagement_engine";
  engagement_task_id: string | null;
  engagement_workflow_type: string | null;
  created_by: string | null;
  extracted_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  document_filename: string | null;
  client_name?: string;
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
  text?: string;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  notes?: string | null;
}

export interface ActionItemCreate {
  text: string;
  client_id: string;
  priority?: string;
  due_date?: string | null;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  notes?: string | null;
}

// ─── Action items API factory ─────────────────────────────────────────────────

export function createActionItemsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list(clientId: string, statusFilter?: string, skip = 0, limit = 50) {
      const params = new URLSearchParams({
        skip: String(skip),
        limit: String(limit),
      });
      if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
      return f<ActionItemListResponse>(
        `/clients/${clientId}/action-items?${params}`
      );
    },

    listPending(clientId: string) {
      return f<ActionItemListResponse>(
        `/clients/${clientId}/action-items/pending`
      );
    },

    update(itemId: string, data: ActionItemUpdate) {
      return f<ActionItem>(`/action-items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    delete(itemId: string) {
      return f<void>(`/action-items/${itemId}`, {
        method: "DELETE",
      });
    },

    reextract(documentId: string) {
      return f<{ message: string }>(
        `/documents/${documentId}/reextract-action-items`,
        { method: "POST" }
      );
    },

    listOrg(params?: Record<string, string>) {
      const qs = params ? `?${new URLSearchParams(params)}` : "";
      return f<ActionItemListResponse>(`/action-items${qs}`);
    },

    create(data: ActionItemCreate) {
      return f<ActionItem>(`/action-items`, {
        method: "POST",
        body: JSON.stringify(data),
      });
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

export interface CommunicationTimelineItem {
  type: "communication";
  id: string;
  date: string;
  title: string;
  subtitle: string;
  icon_hint: string;
  metadata: {
    communication_id: string;
    ai_drafted: boolean;
    template_name?: string;
  } | null;
}

export type TimelineItem = DocumentTimelineItem | ActionItemTimelineItem | CommunicationTimelineItem;

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

export function createTimelineApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list(clientId: string, params?: TimelineParams) {
      const query = new URLSearchParams();
      params?.types?.forEach((t) => query.append("types", t));
      if (params?.start_date) query.set("start_date", params.start_date);
      if (params?.end_date) query.set("end_date", params.end_date);
      if (params?.limit != null) query.set("limit", String(params.limit));
      if (params?.skip != null) query.set("skip", String(params.skip));
      const qs = query.toString();
      return f<TimelineResponse>(
        `/clients/${clientId}/timeline${qs ? `?${qs}` : ""}`
      );
    },
  };
}

// ─── Documents API factory ────────────────────────────────────────────────────
// Call this inside a component after obtaining getToken from useAuth():
//   const { getToken } = useAuth();
//   const api = createDocumentsApi(getToken);

export function createDocumentsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list(clientId: string, skip = 0, limit = 50) {
      return f<DocumentListResponse>(
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
      return f<void>(`/documents/${documentId}`, {
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

export function createIntegrationsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    // ── OAuth ──
    getGoogleAuthUrl() {
      return f<{ authorization_url: string }>(
        "/integrations/google/authorize"
      );
    },

    getMicrosoftAuthUrl() {
      return f<{ authorization_url: string }>(
        "/integrations/microsoft/authorize"
      );
    },

    getZoomAuthUrl() {
      return f<{ authorization_url: string }>(
        "/integrations/zoom/authorize"
      );
    },

    getFrontAuthUrl() {
      return f<{ authorization_url: string }>(
        "/integrations/front/authorize"
      );
    },

    connectFrontToken(apiToken: string) {
      return f<IntegrationConnection>(
        "/integrations/front/connect-token",
        {
          method: "POST",
          body: JSON.stringify({ api_token: apiToken }),
        }
      );
    },

    connectFathom(apiKey: string) {
      return f<IntegrationConnection>(
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
      return f<{ status: string; document_id: string }>(
        "/integrations/fathom/import",
        {
          method: "POST",
          body: formData,
        }
      );
    },

    // ── Connections ──
    listConnections() {
      return f<IntegrationConnection[]>(
        "/integrations/connections"
      );
    },

    disconnect(connectionId: string) {
      return f<void>(
        `/integrations/connections/${connectionId}`,
        { method: "DELETE" }
      );
    },

    // ── Sync ──
    triggerSync(connectionId: string, maxResults = 50, sinceHours = 24) {
      return f<SyncLog>(
        `/integrations/connections/${connectionId}/sync?max_results=${maxResults}&since_hours=${sinceHours}`,
        { method: "POST" }
      );
    },

    triggerDeepSync(connectionId: string) {
      return f<SyncLog>(
        `/integrations/connections/${connectionId}/sync-all`,
        { method: "POST" }
      );
    },

    getSyncHistory(connectionId: string, limit = 20) {
      return f<SyncLog[]>(
        `/integrations/connections/${connectionId}/sync-history?limit=${limit}`
      );
    },

    // ── Routing rules ──
    listRoutingRules() {
      return f<RoutingRule[]>(
        "/integrations/routing-rules"
      );
    },

    createRoutingRule(data: RoutingRuleCreateData) {
      return f<RoutingRule>("/integrations/routing-rules", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    deleteRoutingRule(ruleId: string) {
      return f<void>(`/integrations/routing-rules/${ruleId}`, {
        method: "DELETE",
      });
    },

    autoGenerateRules() {
      return f<RoutingRule[]>(
        "/integrations/routing-rules/auto-generate",
        { method: "POST" }
      );
    },

    // ── Zoom rules ──
    listZoomRules() {
      return f<ZoomRule[]>("/integrations/zoom-rules");
    },

    createZoomRule(data: ZoomRuleCreateData) {
      return f<ZoomRule>("/integrations/zoom-rules", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    deleteZoomRule(ruleId: string) {
      return f<void>(`/integrations/zoom-rules/${ruleId}`, {
        method: "DELETE",
      });
    },

    autoGenerateZoomRules() {
      return f<ZoomRule[]>(
        "/integrations/zoom-rules/auto-generate",
        { method: "POST" }
      );
    },

    // ── Unmatched recordings ──
    listUnmatchedRecordings() {
      return f<UnmatchedRecording[]>(
        "/integrations/zoom/unmatched"
      );
    },

    getAutoSyncStatus() {
      return f<{
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
      }>("/integrations/admin/sync-status");
    },

    assignRecording(documentId: string, clientId: string, createRule?: { match_field: string; match_value: string }) {
      return f<{ status: string }>(
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

export function createOrganizationsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list() {
      return f<Organization[]>("/organizations");
    },

    get(orgId: string) {
      return f<OrgDetail>(`/organizations/${orgId}`);
    },

    update(orgId: string, data: { name?: string; settings?: Record<string, unknown> }) {
      return f<OrgDetail>(`/organizations/${orgId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    listMembers(orgId: string) {
      return f<OrgMember[]>(`/organizations/${orgId}/members`);
    },

    inviteMember(orgId: string, userEmail: string, role: string = "member") {
      return f<OrgMember>(`/organizations/${orgId}/members`, {
        method: "POST",
        body: JSON.stringify({ user_email: userEmail, role }),
      });
    },

    updateMemberRole(orgId: string, userId: string, role: string) {
      return f<OrgMember>(`/organizations/${orgId}/members/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
    },

    removeMember(orgId: string, userId: string) {
      return f<void>(`/organizations/${orgId}/members/${userId}`, {
        method: "DELETE",
      });
    },

    // ── Client access delegation ──

    fetchClientAccess(orgId: string, clientId: string) {
      return f<ClientAccessSummary>(
        `/organizations/${orgId}/clients/${clientId}/access`
      );
    },

    grantClientAccess(orgId: string, clientId: string, userId: string, accessLevel: string = "full") {
      return f<ClientAccess>(
        `/organizations/${orgId}/clients/${clientId}/access`,
        {
          method: "POST",
          body: JSON.stringify({ user_id: userId, access_level: accessLevel }),
        }
      );
    },

    revokeClientAccess(orgId: string, clientId: string, userId: string) {
      return f<void>(
        `/organizations/${orgId}/clients/${clientId}/access/${userId}`,
        { method: "DELETE" }
      );
    },

    restrictClient(orgId: string, clientId: string) {
      return f<ClientAccessSummary>(
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

// ─── Client assignment types ────────────────────────────────────────────────

export interface ClientAssignment {
  id: string;
  client_id: string;
  client_name: string | null;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  org_id: string;
  assigned_by: string;
  assigned_at: string;
  role: string;
}

export interface AssignedClientInfo {
  client_id: string;
  client_name: string;
}

export interface MemberAssignments {
  user_id: string;
  user_name: string;
  user_email: string;
  assigned_clients: AssignedClientInfo[];
}

export interface OrgAssignmentRecord {
  id: string;
  client_id: string;
  client_name: string;
  user_id: string;
  user_name: string;
  user_email: string;
  org_id: string;
  assigned_by: string;
  assigned_at: string;
  role: string;
}

export interface OrgMemberInfo {
  user_id: string;
  name: string;
  email: string;
  role: string;
}

export interface OrgClientInfo {
  id: string;
  name: string;
}

export interface OrgAssignmentsResponse {
  assignments: OrgAssignmentRecord[];
  members: OrgMemberInfo[];
  clients: OrgClientInfo[];
}

export interface MyClientResponse {
  id: string;
  name: string;
  document_count: number;
  action_item_count: number;
}

// ─── Client assignments API factory ─────────────────────────────────────────

export function createClientAssignmentsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list(clientId: string) {
      return f<ClientAssignment[]>(`/clients/${clientId}/assignments`);
    },

    assign(clientId: string, userId: string) {
      return f<ClientAssignment>(`/clients/${clientId}/assignments`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
    },

    remove(clientId: string, userId: string) {
      return f<void>(`/clients/${clientId}/assignments/${userId}`, {
        method: "DELETE",
      });
    },

    /** All assignments across an org with members + clients lists (admin only) */
    listOrgAssignments(orgId: string) {
      return f<OrgAssignmentsResponse>(`/organizations/${orgId}/assignments`);
    },

    /** Bulk-assign members to clients (skips duplicates) */
    bulkAssign(orgId: string, assignments: { client_id: string; user_id: string }[]) {
      return f<ClientAssignment[]>(`/organizations/${orgId}/assignments/bulk`, {
        method: "POST",
        body: JSON.stringify({ assignments }),
      });
    },

    /** Clients assigned to the current user */
    myClients() {
      return f<MyClientResponse[]>(`/users/me/clients`);
    },
  };
}

// ─── Dashboard Summary ──────────────────────────────────────────────────────

export interface DashboardSummary {
  stats: {
    clients: { count: number; limit: number | null };
    action_items: { pending: number; overdue: number; completed_this_week: number };
    documents: { count: number; limit: number | null };
    ai_queries: { used: number; limit: number };
  };
  activity_chart: Array<{ date: string; queries: number }>;
  query_distribution: Array<{ type: string; count: number }>;
  attention_items: Array<{
    id: string;
    description: string;
    client_name: string;
    client_id: string;
    due_date: string | null;
    priority: "critical" | "warning" | "info";
    overdue_days: number | null;
  }>;
  recent_clients: Array<{
    id: string;
    name: string;
    document_count: number;
    action_item_count: number;
    last_activity: string;
  }>;
  team_members: Array<{
    user_id: string;
    name: string;
    email: string;
    role: string;
    queries_used: number;
    last_active: string | null;
  }> | null;
  plan: {
    tier: string;
    billing_interval: string | null;
    seats_used: number | null;
    seats_total: number | null;
  };
  has_completed_onboarding: boolean;
  dismissed_tooltips: string[];
}

export interface PriorityFeedItem {
  type: "action_item" | "strategy_alert" | "inactive_client";
  priority: "critical" | "warning" | "info" | "low";
  title: string;
  subtitle: string;
  client_id: string | null;
  link: string;
}

export interface RevenueImpact {
  total_estimated_savings: number;
  strategies_implemented: number;
  clients_impacted: number;
  monthly_trend: Array<{ month: string; amount: number }>;
}

export interface DeadlineItem {
  id: string;
  text: string;
  client_id: string;
  client_name: string;
  due_date: string;
  overdue_days: number | null;
  priority: "critical" | "warning" | "info";
}

export interface TaskBoardItem {
  id: string;
  text: string;
  client_id: string;
  client_name: string;
  due_date: string | null;
  overdue_days: number | null;
  completed_at: string | null;
  status: "pending" | "completed";
}

export function createDashboardApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    summary: (days = 30) => f<DashboardSummary>(`/dashboard/summary?days=${days}`),
    priorityFeed: () => f<PriorityFeedItem[]>(`/dashboard/priority-feed`),
    revenueImpact: (year: number) => f<RevenueImpact>(`/dashboard/revenue-impact?year=${year}`),
    upcomingDeadlines: () => f<DeadlineItem[]>(`/dashboard/upcoming-deadlines`),
    taskBoardItems: () => f<TaskBoardItem[]>(`/dashboard/taskboard`),
    taskBoardCompleted: (limit = 10) => f<TaskBoardItem[]>(`/dashboard/taskboard/completed?limit=${limit}`),
  };
}

// ─── Tax Strategy Matrix ─────────────────────────────────────────────────────

export interface TaxStrategy {
  id: string;
  name: string;
  category: string;
  description: string | null;
  required_flags: string[];
  display_order: number;
}

export interface StrategyWithStatus {
  strategy: TaxStrategy;
  status: string;
  notes: string | null;
  estimated_impact: number | null;
  tax_year: number;
}

export interface StrategyChecklist {
  tax_year: number;
  client_id: string;
  categories: Array<{
    category_name: string;
    strategies: StrategyWithStatus[];
  }>;
  summary: {
    total_applicable: number;
    total_reviewed: number;
    total_implemented: number;
    total_estimated_impact: number;
  };
}

export interface StrategyHistory {
  strategies: Array<{
    strategy_id: string;
    name: string;
    category: string;
    statuses: Array<{
      tax_year: number;
      status: string;
      notes: string | null;
      estimated_impact: number | null;
    }>;
  }>;
  year_summaries: Array<{
    tax_year: number;
    total_applicable: number;
    total_reviewed: number;
    total_implemented: number;
    total_estimated_impact: number;
  }>;
  available_years: number[];
}

export interface ProfileFlags {
  has_business_entity: boolean;
  has_real_estate: boolean;
  is_real_estate_professional: boolean;
  has_high_income: boolean;
  has_estate_planning: boolean;
  is_medical_professional: boolean;
  has_retirement_plans: boolean;
  has_investments: boolean;
  has_employees: boolean;
}

export interface FlagSuggestion {
  flag: string;
  suggested_value: boolean;
  reason: string;
}

export interface StrategySuggestion {
  strategy_name: string;
  strategy_id: string | null;
  suggested_status: string;
  reason: string;
}

export interface AISuggestResponse {
  flag_suggestions: FlagSuggestion[];
  strategy_suggestions: StrategySuggestion[];
  documents_analyzed: number;
  tax_year: number;
}

export interface ApplySuggestionsRequest {
  accepted_flags: Array<{ flag: string; value: boolean }>;
  accepted_strategies: Array<{ strategy_id: string; status: string; notes?: string }>;
  tax_year: number;
}

export interface ApplySuggestionsResponse {
  flags_updated: number;
  strategies_updated: number;
}

export function createStrategiesApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  const fb = boundFetchBlob(getToken, orgId);
  return {
    /** All active strategies (reference list) */
    listAll: () => f<TaxStrategy[]>("/tax-strategies"),

    /** Strategies applicable to a client for a given year */
    fetchChecklist: (clientId: string, year: number) =>
      f<StrategyChecklist>(`/clients/${clientId}/strategies?year=${year}`),

    /** Upsert a single strategy status */
    updateStatus: (
      clientId: string,
      strategyId: string,
      data: { tax_year: number; status: string; notes?: string | null; estimated_impact?: number | null },
    ) =>
      f<unknown>(`/clients/${clientId}/strategies/${strategyId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    /** Bulk upsert strategy statuses */
    bulkUpdate: (
      clientId: string,
      updates: Array<{
        strategy_id: string;
        tax_year: number;
        status: string;
        notes?: string | null;
        estimated_impact?: number | null;
      }>,
    ) =>
      f<{ updated: number }>(`/clients/${clientId}/strategies/bulk`, {
        method: "PUT",
        body: JSON.stringify({ updates }),
      }),

    /** Year-over-year strategy history */
    fetchHistory: (clientId: string) =>
      f<StrategyHistory>(`/clients/${clientId}/strategies/history`),

    /** Partial update of client profile flags */
    updateFlags: (clientId: string, flags: Partial<ProfileFlags>) =>
      f<ProfileFlags>(`/clients/${clientId}/profile-flags`, {
        method: "PATCH",
        body: JSON.stringify(flags),
      }),

    /** AI-powered strategy suggestions */
    aiSuggestStrategies: (clientId: string) =>
      f<AISuggestResponse>(
        `/clients/${clientId}/strategies/ai-suggest`,
        { method: "POST" },
      ),

    /** Apply accepted AI suggestions */
    applySuggestions: (clientId: string, data: ApplySuggestionsRequest) =>
      f<ApplySuggestionsResponse>(
        `/clients/${clientId}/strategies/ai-suggest/apply`,
        { method: "POST", body: JSON.stringify(data) },
      ),

    /** Generate strategy impact report PDF */
    generateReport: (clientId: string, year: number, includePriorYears: boolean) =>
      fb(`/clients/${clientId}/strategies/report`, {
        method: "POST",
        body: JSON.stringify({ year, include_prior_years: includePriorYears }),
      }),
  };
}

// ─── Strategy Dashboard ──────────────────────────────────────────────────────

export interface StrategyOverview {
  total_clients: number;
  clients_reviewed: number;
  clients_unreviewed: number;
  total_implemented: number;
  total_estimated_impact: number;
}

export interface ClientStrategySummary {
  client_id: string;
  client_name: string;
  client_type: string | null;
  active_flags: string[];
  total_applicable: number;
  total_reviewed: number;
  total_implemented: number;
  total_estimated_impact: number;
  coverage_pct: number;
  last_reviewed_at: string | null;
}

export interface StrategyAdoption {
  strategy_id: string;
  strategy_name: string;
  category: string;
  total_applicable: number;
  total_implemented: number;
  total_recommended: number;
  total_declined: number;
  adoption_rate: number;
}

export interface UnreviewedAlert {
  client_id: string;
  client_name: string;
  strategy_id: string;
  strategy_name: string;
  category: string;
}

export function createStrategyDashboardApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    fetchOverview: (year: number) =>
      f<StrategyOverview>(`/strategy-dashboard/overview?year=${year}`),

    fetchClients: (year: number) =>
      f<ClientStrategySummary[]>(`/strategy-dashboard/clients?year=${year}`),

    fetchAdoption: (year: number) =>
      f<StrategyAdoption[]>(`/strategy-dashboard/adoption?year=${year}`),

    fetchAlerts: (year: number) =>
      f<UnreviewedAlert[]>(`/strategy-dashboard/alerts?year=${year}`),
  };
}

// ─── Communication types ─────────────────────────────────────────────────────

export interface ClientCommunication {
  id: string;
  client_id: string;
  user_id: string;
  communication_type: string;
  subject: string;
  body_html: string;
  body_text: string | null;
  recipient_email: string;
  recipient_name: string | null;
  template_id: string | null;
  status: string;
  resend_message_id: string | null;
  metadata: Record<string, unknown> | null;
  thread_id: string | null;
  thread_type: string | null;
  thread_year: number | null;
  thread_quarter: number | null;
  open_items: OpenItemData[] | null;
  open_items_resolved: Record<string, unknown>[] | null;
  sent_at: string;
  created_at: string;
}

export interface OpenItemData {
  question: string;
  asked_in_email_id: string;
  asked_date: string;
  status: "open" | "resolved" | "superseded";
  resolved_in_email_id: string | null;
  resolved_date: string | null;
}

export interface QuarterlyEstimateDraftResponse {
  subject: string;
  body_html: string;
  body_text: string;
  thread_id: string;
  thread_type: string;
  thread_year: number;
  thread_quarter: number;
  open_items_from_prior: { question: string; status: string }[];
  financial_context_used: Record<string, unknown>[];
}

export interface EmailTemplate {
  id: string;
  user_id: string | null;
  name: string;
  subject_template: string;
  body_template: string;
  template_type: string;
  is_default: boolean;
  is_active: boolean;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface FollowUpReminder {
  id: string;
  communication_id: string;
  client_id: string;
  user_id: string;
  remind_at: string;
  status: string;
  triggered_at: string | null;
  created_at: string;
}

export interface CommunicationSendRequest {
  subject: string;
  body_html: string;
  recipient_email: string;
  recipient_name?: string;
  template_id?: string;
  follow_up_days?: number;
  metadata?: Record<string, unknown>;
  thread_id?: string;
  thread_type?: string;
  thread_year?: number;
  thread_quarter?: number;
}

export interface CommunicationSendResponse {
  communication: ClientCommunication;
  follow_up: FollowUpReminder | null;
}

export interface DraftEmailRequest {
  purpose: string;
  additional_context?: string;
}

export interface DraftEmailResponse {
  subject: string;
  body_html: string;
  body_text: string;
  ai_drafted: boolean;
}

export interface RenderTemplateRequest {
  template_id: string;
  extra_vars?: Record<string, string>;
}

export interface RenderedTemplate {
  subject: string;
  body_html: string;
}

export interface SchedulingUrlResponse {
  scheduling_url: string | null;
}

// ─── Communications API factory ──────────────────────────────────────────────

export function createCommunicationsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    sendEmail(clientId: string, data: CommunicationSendRequest) {
      return f<CommunicationSendResponse>(`/clients/${clientId}/communications/send`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    getHistory(clientId: string, limit = 20) {
      return f<ClientCommunication[]>(`/clients/${clientId}/communications?limit=${limit}`);
    },

    getLastCommunication(clientId: string) {
      return f<ClientCommunication | null>(`/clients/${clientId}/communications/last`);
    },

    renderTemplate(clientId: string, data: RenderTemplateRequest) {
      return f<RenderedTemplate>(`/clients/${clientId}/communications/render-template`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    draftWithAI(clientId: string, data: DraftEmailRequest) {
      return f<DraftEmailResponse>(`/clients/${clientId}/communications/draft`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    getTemplates() {
      return f<EmailTemplate[]>("/communications/templates");
    },

    createTemplate(data: { name: string; subject_template: string; body_template: string; template_type: string }) {
      return f<EmailTemplate>("/communications/templates", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    updateTemplate(id: string, data: Partial<{ name: string; subject_template: string; body_template: string; template_type: string }>) {
      return f<EmailTemplate>(`/communications/templates/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    deleteTemplate(id: string) {
      return f<void>(`/communications/templates/${id}`, { method: "DELETE" });
    },

    resolveFollowUp(id: string) {
      return f<FollowUpReminder>(`/follow-up-reminders/${id}/resolve`, { method: "POST" });
    },

    dismissFollowUp(id: string) {
      return f<FollowUpReminder>(`/follow-up-reminders/${id}/dismiss`, { method: "POST" });
    },

    updateSchedulingUrl(url: string | null) {
      return f<SchedulingUrlResponse>("/users/me/scheduling-url", {
        method: "PATCH",
        body: JSON.stringify({ scheduling_url: url }),
      });
    },

    draftQuarterlyEstimate(clientId: string, taxYear: number, quarter: number) {
      return f<QuarterlyEstimateDraftResponse>(
        `/clients/${clientId}/communications/draft-quarterly-estimate`,
        {
          method: "POST",
          body: JSON.stringify({ tax_year: taxYear, quarter }),
        },
      );
    },

    getThreadHistory(clientId: string, threadId: string) {
      return f<ClientCommunication[]>(
        `/clients/${clientId}/communications/thread/${threadId}`,
      );
    },
  };
}

// ─── Extension types ─────────────────────────────────────────────────────────

export interface ExtensionConfig {
  tier: string;
  auto_match: boolean;
  quick_query: boolean;
  parsers: boolean;
  monitoring: boolean;
  captures_per_day: number | null;
  captures_today: number;
  captures_remaining: number | null;
}

export interface ExtensionCapture {
  document_id: string;
  client_id: string;
  client_name: string;
  filename: string;
  capture_type: string | null;
  source_url: string | null;
  created_at: string;
  processed: boolean;
}

export interface ExtensionCaptureStats {
  today_count: number;
  month_count: number;
  top_clients: { client_id: string; client_name: string; capture_count: number }[];
}

export interface MonitoringRule {
  id: string;
  rule_name: string;
  rule_type: string;
  pattern: string;
  client_id: string;
  client_name: string | null;
  is_active: boolean;
  notify_only: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface MonitoringRuleCreate {
  rule_name: string;
  rule_type: string;
  pattern: string;
  client_id: string;
  notify_only?: boolean;
}

export interface MonitoringRuleUpdate {
  rule_name?: string;
  rule_type?: string;
  pattern?: string;
  client_id?: string;
  notify_only?: boolean;
  is_active?: boolean;
}

// ─── Extension API factory ───────────────────────────────────────────────────

export function createExtensionApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    getConfig() {
      return f<ExtensionConfig>("/extension/config");
    },

    getRecentCaptures(limit = 20) {
      return f<ExtensionCapture[]>(`/extension/recent-captures?limit=${limit}`);
    },

    getCaptureStats() {
      return f<ExtensionCaptureStats>("/extension/capture-stats");
    },

    getMonitoringRules() {
      return f<MonitoringRule[]>("/extension/monitoring-rules");
    },

    createMonitoringRule(data: MonitoringRuleCreate) {
      return f<MonitoringRule>("/extension/monitoring-rules", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    updateMonitoringRule(ruleId: string, data: MonitoringRuleUpdate) {
      return f<MonitoringRule>(`/extension/monitoring-rules/${ruleId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      });
    },

    deleteMonitoringRule(ruleId: string) {
      return f<void>(`/extension/monitoring-rules/${ruleId}`, { method: "DELETE" });
    },
  };
}

// ─── Notification preferences ─────────────────────────────────────────────────

export interface NotificationPreferences {
  id: string;
  user_id: string;
  org_id: string;
  task_assigned: boolean;
  task_completed: boolean;
  deadline_reminder: boolean;
  deadline_reminder_days: number;
  daily_digest: boolean;
}

export function createNotificationsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    getPreferences() {
      return f<NotificationPreferences>("/notifications/preferences");
    },
    updatePreferences(data: Partial<NotificationPreferences>) {
      return f<NotificationPreferences>("/notifications/preferences", {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
  };
}

// ─── Onboarding ──────────────────────────────────────────────────────────────

export interface OnboardingStatus {
  has_completed_onboarding: boolean;
}

export function createOnboardingApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    complete() {
      return f<OnboardingStatus>("/users/onboarding", {
        method: "PATCH",
        body: JSON.stringify({ completed: true }),
      });
    },
  };
}

// ─── Tooltips ────────────────────────────────────────────────────────────────

export function createTooltipsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    dismiss(tooltipId: string) {
      return f<{ dismissed_tooltips: string[] }>("/users/tooltips", {
        method: "PATCH",
        body: JSON.stringify({ tooltip_id: tooltipId, action: "dismiss" }),
      });
    },
  };
}

// ─── Journal ────────────────────────────────────────────────────────────────

export interface JournalEntry {
  id: string;
  client_id: string;
  user_id: string;
  entry_type: string;
  category: string | null;
  title: string;
  content: string | null;
  effective_date: string | null;
  source_type: string | null;
  source_id: string | null;
  metadata: Record<string, unknown> | null;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface JournalFeedResponse {
  entries: JournalEntry[];
  total: number;
}

export interface JournalEntryCreateData {
  title: string;
  content?: string;
  entry_type?: string;
  category?: string;
  effective_date?: string;
  is_pinned?: boolean;
}

export interface JournalEntryUpdateData {
  title?: string;
  content?: string;
  category?: string;
  effective_date?: string;
  is_pinned?: boolean;
}

export function createJournalApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    list(clientId: string, params?: Record<string, string>) {
      const qs = params ? "?" + new URLSearchParams(params).toString() : "";
      return f<JournalFeedResponse>(`/clients/${clientId}/journal${qs}`);
    },

    create(clientId: string, data: JournalEntryCreateData) {
      return f<JournalEntry>(`/clients/${clientId}/journal`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    update(entryId: string, data: JournalEntryUpdateData) {
      return f<JournalEntry>(`/journal/${entryId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    delete(entryId: string) {
      return f<void>(`/journal/${entryId}`, { method: "DELETE" });
    },

    togglePin(entryId: string) {
      return f<JournalEntry>(`/journal/${entryId}/pin`, { method: "PATCH" });
    },
  };
}

// ─── Engagement types ─────────────────────────────────────────────────────────

export interface EngagementTemplateTask {
  id: string;
  task_name: string;
  category: string | null;
  recurrence: string;
  month: number | null;
  day: number | null;
  lead_days: number;
  priority: string;
  display_order: number;
}

export interface EngagementTemplate {
  id: string;
  name: string;
  description: string | null;
  entity_types: string[] | null;
  is_system: boolean;
  is_active: boolean;
  tasks: EngagementTemplateTask[];
}

export interface ClientEngagement {
  id: string;
  client_id: string;
  template: EngagementTemplate;
  start_year: number;
  is_active: boolean;
  custom_overrides: Record<string, unknown> | null;
  created_at: string;
  created_by: string | null;
}

export interface AssignEngagementData {
  template_id: string;
  start_year?: number;
  custom_overrides?: Record<string, unknown>;
}

export interface CreateTemplateData {
  name: string;
  description?: string;
  entity_types?: string[];
}

export interface GenerateTasksResponse {
  tasks_created: number;
  details: Record<string, unknown>[];
}

export function createEngagementsApi(getToken: GetToken, orgId?: string) {
  const f = boundFetch(getToken, orgId);
  return {
    listTemplates() {
      return f<EngagementTemplate[]>("/engagement-templates");
    },

    createTemplate(data: CreateTemplateData) {
      return f<EngagementTemplate>("/engagement-templates", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    listClientEngagements(clientId: string) {
      return f<ClientEngagement[]>(`/clients/${clientId}/engagements`);
    },

    assignEngagement(clientId: string, data: AssignEngagementData) {
      return f<ClientEngagement>(`/clients/${clientId}/engagements`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    removeEngagement(clientId: string, engagementId: string) {
      return f<void>(`/clients/${clientId}/engagements/${engagementId}`, {
        method: "DELETE",
      });
    },

    generateTasks(clientId: string) {
      return f<GenerateTasksResponse>(
        `/clients/${clientId}/engagements/generate`,
        { method: "POST" },
      );
    },
  };
}

// ─── useApi hook ─────────────────────────────────────────────────────────────
// Reads orgId from OrgContext and returns pre-configured API instances so pages
// don't have to manually pass orgId every time.
//
// NOTE: This hook must be imported as a standalone module to avoid circular
// imports (OrgContext imports from api.ts).  It is declared in lib/useApi.ts.
