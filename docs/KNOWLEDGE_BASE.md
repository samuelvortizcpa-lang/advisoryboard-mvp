# Callwen Knowledge Base

**Last updated:** 2026-03-28
**Purpose:** Comprehensive reference for every AI coding session on this codebase.

---

## 1. Domain Knowledge

### IRC Section 7216 — Tax Return Information Disclosure

IRC Section 7216 governs how tax return preparers can use and disclose taxpayer information. Callwen enforces compliance through a tiered consent system.

**Three Consent Tiers:**

| Tier | Who | What's Required | Consent Document |
|------|-----|-----------------|-----------------|
| `full_7216` | Tax preparers (`is_tax_preparer=true`) | Full §7216 consent form with e-signature | IRS-compliant disclosure + consent language |
| `aicpa_acknowledgment` | Advisory-only CPAs (`is_tax_preparer=false`) | AICPA professional acknowledgment | Lighter acknowledgment form |
| `not_required` | Default (no tax documents) | Nothing | N/A |

**Consent Status Lifecycle:**
```
not_required
  ↓ (tax document uploaded, is_tax_preparer not set)
determination_needed
  ↓ (user confirms is_tax_preparer=true)     ↓ (user confirms is_tax_preparer=false)
pending                                       advisory_acknowledgment_needed
  ↓ (consent form sent)                        ↓ (client signs acknowledgment)
sent                                          acknowledged
  ↓ (client signs)
obtained
  ↓ (1 year passes)
expired
```

Also possible: `declined` (client refuses consent).

**E-Signature Flow:**
1. CPA creates consent request → `ClientConsent` row created
2. System generates 48-byte signing token (unique, indexed)
3. Email sent to client with link: `/consent/sign/{token}`
4. Public page (no auth required) validates token + checks 30-day expiry
5. Client signs → status becomes `obtained`, `signed_at` recorded
6. Signed PDF generated via ReportLab, stored in Supabase Storage
7. Consent valid for 1 year from `signed_at`

**Key Files:**
- `backend/app/services/consent_service.py` — Core consent logic
- `backend/app/models/client_consent.py` — Consent ORM model
- `backend/app/api/consents.py` — Protected consent endpoints
- `backend/app/api/consent_public.py` — Public signature endpoint (no auth)

**Compliance Rules (never break these):**
- Tax preparers MUST have full §7216 consent before AI processes their tax documents
- Consent expires after 1 year and must be renewed
- The `is_tax_preparer` flag on Client determines which tier applies
- Advisory-only CPAs use the lighter AICPA acknowledgment, not full §7216

### CPA Workflows

**Document Types Callwen Handles:**
- Tax returns (Form 1040, 1120, 1065, K-1, W-2)
- Financial statements (P&L, balance sheet, cash flow)
- Engagement letters
- Meeting recordings (Zoom transcripts)
- Email correspondence (Gmail, Outlook)
- Front CRM conversations

**How CPAs Use Callwen:**
1. Upload client documents (tax returns, financials)
2. System auto-classifies and extracts text + action items
3. Ask natural-language questions ("What's this client's AGI?")
4. Get source-cited answers referencing specific forms and line items
5. Track action items with due dates
6. Generate meeting prep briefs
7. Monitor consent status for compliance

### Tax Terminology (Built Into RAG)

The `tax_terms.py` service expands common abbreviations for better semantic search:
- AGI → Adjusted Gross Income (Form 1040 Line 11)
- MAGI → Modified Adjusted Gross Income
- QBI → Qualified Business Income (Form 8995)
- SE tax → Self-Employment Tax (Schedule SE)
- K-1 box numbers → specific income/deduction categories

Financial document chunks use smaller chunk sizes (500 chars / 100 overlap) vs default (1500 / 200) for precision on line-item lookups.

---

## 2. Architecture

### System Overview

```
User Browser
  ↓
callwen.com (Vercel, Next.js 14)
  ├── /__clerk/* → clerk.callwen.com (auth proxy)
  ├── /dashboard/* → client-side React app
  └── /api/* → advisoryboard-mvp-production.up.railway.app (FastAPI)
                ├── PostgreSQL + pgvector (Supabase)
                ├── OpenAI API (embeddings + GPT-4o)
                ├── Anthropic API (Claude Sonnet/Opus)
                ├── Supabase Storage (files)
                └── External APIs (Gmail, Outlook, Zoom, Front, Stripe)
```

### Authentication Flow

```
1. Browser → Clerk JS SDK (clerk.callwen.com)
2. Clerk issues JWT (RS256, signed with Clerk's private key)
3. Frontend sends JWT as Bearer token to FastAPI
4. Backend verifies:
   a. Fetch JWKS from clerk.callwen.com/.well-known/jwks.json (cached)
   b. Look up RSA public key by kid
   c. Verify RS256 signature
   d. Decode payload → user_id, email, session_id
5. AuthContext resolves:
   a. Mirror user in local DB (User table)
   b. Resolve org: X-Org-Id header → firm org preference → personal fallback
   c. Verify org membership (OrganizationMember.is_active=true)
   d. Return AuthContext(user_id, org_id, org_role, is_personal_org)
```

**Test Mode:** When `TEST_MODE=true`, bearer token matching `CLERK_SECRET_KEY` bypasses all Clerk verification. Must never reach production.

**Key Files:**
- `backend/app/core/auth.py` — JWT verification, JWKS caching, @require_auth decorator
- `backend/app/services/auth_context.py` — AuthContext dataclass, org resolution, access checks
- `frontend/middleware.ts` — Clerk proxy through callwen.com/__clerk

### Multi-Tenancy Isolation

**Primary isolation key:** `org_id` (UUID FK to Organizations table)

**Models with direct org_id:** Client, ClientAssignment, IntegrationConnection, UserSubscription, TokenUsage

**Models scoped via client_id (inherited isolation):** Document, DocumentChunk, DocumentPageImage, ActionItem, ChatMessage, ClientConsent, ClientBrief, ClientStrategyStatus, Interaction

**Global models (no tenant scope):** User, ClientType, TaxStrategy, ProcessedWebhookEvent

**Access control layers:**
1. `org_id` filter on every query (base isolation)
2. `OrganizationMember` — user must be active member of org
3. `ClientAssignment` — optional fine-grained client assignment
4. `ClientAccess` — per-client permission levels (full/readonly/none)
5. `require_admin(auth)` — admin-only operations

**Org types:** `personal` (single user) or `firm` (team workspace with seats)

### RAG Pipeline

**Upload Pipeline:** `process_document()` in `rag_service.py`

| Stage | Service | Timing (50-page PDF) |
|-------|---------|---------------------|
| 1. Download from Supabase | `document_service.py` | ~800ms |
| 2. Text extraction | `text_extraction.py` (pdfplumber) | ~2.5s |
| 2b. OCR fallback | Tesseract at 150 DPI | **~250-750s** |
| 3. Document classification | `document_classifier.py` (GPT-4o-mini) | ~300ms |
| 4. Chunking | `chunking.py` | ~100ms |
| 5. Embedding | OpenAI `text-embedding-3-small` (batches of 100) | ~300-600ms |
| 6. Bulk insert | pgvector DocumentChunk rows | ~300ms |
| 7. Action item extraction | `action_item_extractor.py` (GPT-4o-mini) | ~2s |
| 8. Page image processing | `page_image_service.py` (pdf2image + OCR) | ~150s |
| 9. Version check | `_check_supersede()` | <10ms |

**OCR is the biggest bottleneck.** IRS forms often trigger the garbled-text detector (reversed words, CID references). When OCR kicks in, a 50-page return takes 4-12 minutes.

**Query Pipeline:** `answer_question()` in `rag_service.py`

| Stage | Timing | Notes |
|-------|--------|-------|
| 1. Query classification | 100-300ms | GPT-4o-mini routes factual vs strategic |
| 2. Financial term expansion | <5ms | Local dictionary, no API call |
| 3. Embed query | 150-250ms | 1-2 embeddings (original + expanded) |
| 4. HNSW vector search (x2) | 100-500ms | Two searches run **sequentially** |
| 5. Keyword fallback (ILIKE) | 50-200ms | Up to 8 phrase searches |
| 6. Context assembly | <5ms | String concatenation |
| 7. LLM completion | 1-8s | Model-dependent |
| 8. Page matching | <10ms | Local scoring |
| **Total (factual)** | **~2-4s** | GPT-4o-mini |
| **Total (strategic)** | **~3-6s** | Claude Sonnet |
| **Total (opus)** | **~4-10s** | Claude Opus |

**No streaming responses.** Users see a spinner until the complete response arrives. Streaming would cut perceived latency by 60-70%.

**Vector Index:** HNSW on `document_chunks.embedding` with `m=16, ef_construction=64, vector_cosine_ops`. Correct choice for datasets under 1M vectors. `ef_search` at default 40, could benefit from raising to 100 for better recall on financial docs.

### Stripe Integration

**Checkout Flow:**
```
1. Frontend calls POST /api/stripe/create-checkout (tier, billing_interval, addon_seats)
2. Backend creates Stripe Checkout session with line items
3. User redirected to Stripe-hosted checkout page
4. On success, Stripe sends checkout.session.completed webhook
5. Backend creates/updates UserSubscription with stripe_customer_id, stripe_subscription_id
6. Org max_members synced to tier's seat limit
```

**Webhook Events Handled:**
- `checkout.session.completed` → create subscription
- `customer.subscription.updated` → sync tier/seats/billing period
- `customer.subscription.deleted` → downgrade to free
- `invoice.payment_failed` → mark past_due, Slack notification
- `invoice.payment_succeeded` → log only

**Idempotency:** `ProcessedWebhookEvent` table stores processed event IDs. Duplicate events are silently skipped. Processing failures return HTTP 500 so Stripe retries.

### OAuth Integrations (4 providers)

**State Token (CSRF protection):** HMAC-signed, stateless. Format: `base64url(JSON{uid, nonce, ts}).HMAC-SHA256`. TTL: 10 minutes. Verified with constant-time comparison.

| Provider | Scopes | What Syncs |
|----------|--------|-----------|
| Gmail | gmail.readonly | Emails → Documents (via routing rules) |
| Outlook | Mail.ReadWrite | Emails → Documents (via routing rules) |
| Zoom | meeting:read | Recordings + transcripts → Documents |
| Front | conversation.list, contact.read | Conversations → Documents |

**Sync Lifecycle:** APScheduler triggers periodic sync → fetch new items from provider API → match to client via routing rules (EmailRoutingRule / ZoomMeetingRule) → create Document → trigger RAG pipeline.

**Token Storage:** `IntegrationConnection` model stores encrypted access/refresh tokens. Unique constraint: (user_id, provider, provider_email).

### API Structure

21 router files, 125+ endpoints registered in `backend/main.py`:

| Router | Prefix | Purpose |
|--------|--------|---------|
| clients | /api | Core client CRUD |
| documents | /api | Upload, list, delete |
| rag | /api | Q&A (semantic search + LLM) |
| consents | /api | §7216 consent management |
| consent_public | /api/consent | Public signature (no auth) |
| stripe_routes | /api/stripe | Billing, webhooks |
| integrations | /api | OAuth flow, connections |
| organizations | /api | Create/switch orgs, invite |
| alerts | /api | Client alerts |
| action_items | /api | Task tracking |
| chat_messages | /api | Chat history |
| briefs | /api | Meeting prep briefs |
| dashboard | /api | Home page stats |
| strategies | /api | Tax strategy management |
| strategy_dashboard | /api | Strategy recommendations |
| timeline | /api | Client interaction history |
| usage | /api | Token cost reporting |
| client_assignments | /api | Work assignments |
| client_access | /api | Per-client permissions |
| client_types | /api | AI prompt categories |
| health | /api | Healthcheck (no auth) |
| admin | /api/admin | Admin dashboard |

---

## 3. Business Logic

### Subscription Tiers

| Feature | Free | Starter | Professional | Firm |
|---------|------|---------|-------------|------|
| Price (monthly) | $0 | ~$99 | ~$149 | $349 base |
| Clients | 5 | 25 | 100 | Unlimited |
| Documents | Unlimited | Unlimited | Unlimited | Unlimited |
| Seats | 1 | 1 | 3 | 3 base + add-ons |
| Strategic queries/mo | 50 | 0 | 100 | 500 |
| Opus queries/mo | 0 | 0 | 10 | 50 |
| Models available | GPT-4o-mini only | GPT-4o-mini only | + Claude models | + Claude models |
| Add-on seats | No | No | No | $79/mo or $63/mo annual |

**Stripe Price IDs** configured via env vars: `stripe_price_starter`, `stripe_price_professional`, `stripe_price_firm_hybrid_monthly`, `stripe_price_addon_seat_monthly`, plus annual variants.

**Legacy pricing:** Old per-seat Firm ($249/seat) still supported for backward compat. When detected, grants 3 base seats with 0 add-ons.

### Subscription Lifecycle

```
No subscription (tier="free", 50 strategic queries)
  ↓ checkout.session.completed
Active (tier=chosen, stripe_status="active")
  ↓ invoice.payment_failed
Past Due (stripe_status="past_due", payment_status="failed")
  ↓ customer.subscription.deleted
Canceled (tier="free", stripe_status="canceled", queries reset to 0)
```

**Billing period reset:** Auto-resets `strategic_queries_used=0` when `billing_period_end` passes. Checked on every `get_or_create_subscription()` call.

**Seat management:** Firm tier supports add-on seats via `SubscriptionItem.modify()` with proration. Org `max_members` synced after changes.

### Query Quota System

- **Strategic queries:** Counter on `UserSubscription.strategic_queries_used`, incremented atomically
- **Opus queries:** Counted from `TokenUsage` table (model="claude-opus-4-20250514" within billing period)
- **Factual queries (GPT-4o-mini):** No quota, always allowed
- **Enforcement:** `check_quota()` returns `{allowed, tier, used, limit, remaining}` before each strategic/opus call

### Alert System

7 alert types computed on demand (not stored):

| Type | Severity | Trigger |
|------|----------|---------|
| overdue_action | critical | Action item past due date |
| upcoming_deadline | warning | Action item due within 7 days |
| consent_needed | warning | Tax preparer without §7216 consent |
| stuck_document | warning | Document processing failed |
| preparer_determination_needed | info | Tax docs uploaded, no preparer flag set |
| consent_expiring | info | Consent expires within 30 days |
| stale_client | info | No documents or chats in 30 days |

Alerts can be dismissed per-user via `DismissedAlert` table.

### Document Processing Details

**Supported formats:** PDF, DOCX, DOC, XLSX, XLS, PPTX, TXT, CSV, JSON, MP4, M4A, MP3, WAV, EML, MSG

**Size limits:** 50 MB (regular), 500 MB (audio/video)

**Duplicate prevention:** Filename + client_id must be unique. Gmail deduped by `gmail_message_id`. Outlook/Zoom deduped by `external_id`.

**Document versioning:** Newer docs of same type+subtype supersede older ones. Compares `document_period` strings. Old doc marked `is_superseded=true`.

**Action item extraction:** GPT-4o-mini extracts `{text, due_date, priority}` from document text (truncated to 80K chars). Non-fatal on failure.

### Notification System

Slack webhooks for key events (fire-and-forget, non-blocking):
- `new_signup` — New user created
- `upgrade` — Subscription purchased
- `churn` — Subscription canceled
- `payment_failed` — Payment declined
- `limit_hit` — Client or query limit reached

### Admin Dashboard

Protected by `ADMIN_API_KEY` header or `ADMIN_USER_ID` Clerk JWT. Endpoints:
- `GET /api/admin/users` — All users with metrics (client count, doc count, queries, cost, last active)
- `GET /api/admin/overview` — Platform stats (users by tier, MRR, active users)
- `GET /api/admin/subscriptions` — Subscription list with usage %
- `PUT /api/admin/subscriptions/{user_id}` — Override tier
- `POST /api/admin/subscriptions/{user_id}/reset-usage` — Reset quota

---

## 4. Conventions

### Frontend

**Styling:** Tailwind utility classes + inline `style={{}}` for custom values. **Never use `styled-jsx`** (fails with child components / dynamic content). Keyframe animations use plain `<style dangerouslySetInnerHTML>` tags.

**Fonts:** Cormorant Garamond (serif, headlines) and Outfit (sans, body) via `next/font/google`.

**API client:** All backend calls go through `frontend/lib/api.ts`. Factory functions per resource: `createClientsApi(getToken, orgId)` returns `{ list, get, create, update, delete }`. Used via `useApi()` hook which binds active org + Clerk token.

**Org context:** `OrgContext.tsx` manages multi-tenant org switching. Prefers firm org over personal workspace. Exposes `activeOrg`, `isAdmin`, `isPersonalOrg`, `setActiveOrg()`.

**Component structure:** `frontend/components/` organized by domain: action-items, alerts, auth, briefs, clients, consent, dashboard, documents, layout, rag, strategies, timeline, ui.

**Dynamic rendering:** `export const dynamic = 'force-dynamic'` in root layout.

### Backend

**Route handler pattern:**
```python
@router.get("/path", response_model=ResponseSchema)
async def handler(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ResponseSchema:
    # auth.org_id, auth.user_id, auth.org_role available
    return service_function(db, org_id=auth.org_id, ...)
```

**Service layer:** Business logic in `backend/app/services/`, never in route handlers. Pure functions taking `db: Session` + params. Naming: `get_*`, `create_*`, `update_*`, `delete_*`.

**Models:** SQLAlchemy 2.0 with `Mapped[]` type annotations. UUIDs as primary keys (`default=uuid.uuid4`). `server_default=func.now()` for timestamps. `ForeignKey(..., ondelete="CASCADE")` with `relationship(back_populates=...)`.

**Schemas:** Pydantic v2. Pattern: `Base → Create → Update → Response`. Response schemas use `from_attributes = True` for ORM compatibility.

**Configuration:** Pydantic `BaseSettings` with `@lru_cache` singleton. 40+ env vars. Production safety guard forces `test_mode=False`.

**Error handling:** `HTTPException(status_code=..., detail="message")`. Sentry captures exceptions. 10% trace/profile sampling.

### Database

**Pool:** `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`. Max 15 simultaneous connections. Sync SQLAlchemy (not async).

**Migrations:** Alembic. 30+ versions. Auto-run before server start via Procfile. Naming: `YYYYMMDD_HHMM_revid_slug.py`.

**Key indexes:** User.clerk_id (unique), Document.gmail_message_id (unique), DocumentChunk HNSW embedding index, TokenUsage composite indexes on (user_id+created_at), (client_id), (model).

### Deployment

**Backend (Railway):**
```
Procfile: web: cd backend && mkdir -p uploads && alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
```
System packages: Python 3.13, FFmpeg, Tesseract, poppler-utils (via nixpacks.toml).

**Frontend (Vercel):** Deployed via push to `vercel-deploy` remote. `NEXT_PUBLIC_API_URL` baked at build time. Sentry source maps uploaded when `SENTRY_AUTH_TOKEN` set.

**Deploy workflow:**
```bash
cd frontend && npx tsc --noEmit  # verify TypeScript compiles
git push origin main && git push vercel-deploy main
```

**Two remotes:** `origin` (samuelvortizcpa-lang) and `vercel-deploy` (samuelvortizcpa-code).

### Testing

**Framework:** pytest + pytest-asyncio. Limited coverage (one integration test for client isolation).

**Test mode:** `TEST_MODE=true` + `CLERK_SECRET_KEY` as bearer token bypasses Clerk JWT verification.

---

## 5. Performance Profile

From benchmark report (2026-03-28, code-path analysis):

### Upload Pipeline
| Document | Normal | OCR Fallback |
|----------|--------|-------------|
| 1-page | ~1.2s | ~9s |
| 10-page | ~2.3s | ~85s |
| 50-page | **~6.5s** | **~400s+** |

**Bottleneck:** Tesseract OCR at 150 DPI (5-15s/page).

### Query Pipeline
| Model | Avg Response Time |
|-------|------------------|
| GPT-4o-mini (factual) | ~2-4s |
| Claude Sonnet (strategic) | **~3-6s** |
| Claude Opus (deep) | **~4-10s** |

**Bottleneck:** LLM completion time. No streaming implemented.

### Concurrency
| Users | Avg Query Time | Status |
|-------|---------------|--------|
| 1 | ~3s | OK |
| 5 | ~4s | OK |
| 10 | **~6s** | DEGRADED |
| 20 | **~10s+** | BOTTLENECK |

**Bottleneck:** Sync SQLAlchemy on async FastAPI with only 2 workers.

### P0 Recommendations
1. **Streaming responses** — 60-70% perceived latency reduction
2. **Parallel vector searches** — Save ~200ms/query (asyncio.gather)
3. **Raise ef_search to 100** — Better recall on financial docs (+50ms)

---

## 6. Key File Index

### Core
| File | Purpose |
|------|---------|
| `backend/main.py` | App entry, 21 routers, CORS, Sentry, APScheduler |
| `backend/app/core/auth.py` | Clerk JWT verification, JWKS cache |
| `backend/app/core/config.py` | Pydantic Settings (40+ env vars) |
| `backend/app/core/database.py` | SQLAlchemy engine, session factory |
| `backend/app/services/auth_context.py` | AuthContext, org resolution |
| `frontend/middleware.ts` | Clerk proxy middleware |
| `frontend/lib/api.ts` | 18 API factory functions |
| `frontend/contexts/OrgContext.tsx` | Org switching context |

### RAG Pipeline
| File | Purpose |
|------|---------|
| `backend/app/services/rag_service.py` | Upload + query pipeline |
| `backend/app/services/chunking.py` | Text chunking (adaptive sizes) |
| `backend/app/services/text_extraction.py` | Multi-format extraction |
| `backend/app/services/document_classifier.py` | GPT-4o-mini classification |
| `backend/app/services/query_router.py` | Factual vs strategic routing |
| `backend/app/services/tax_terms.py` | Financial term expansion |
| `backend/app/services/page_image_service.py` | PDF page snapshots |
| `backend/app/services/action_item_extractor.py` | GPT-4o-mini extraction |

### Billing & Consent
| File | Purpose |
|------|---------|
| `backend/app/services/stripe_service.py` | Stripe API, checkout, webhooks |
| `backend/app/services/subscription_service.py` | Tiers, quotas, seats |
| `backend/app/api/stripe_routes.py` | Billing endpoints |
| `backend/app/services/consent_service.py` | §7216 consent logic |
| `backend/app/services/oauth_state.py` | HMAC-signed OAuth state tokens |

### Integrations
| File | Purpose |
|------|---------|
| `backend/app/services/google_auth_service.py` | Gmail OAuth |
| `backend/app/services/microsoft_auth_service.py` | Outlook OAuth |
| `backend/app/services/zoom_auth_service.py` | Zoom OAuth |
| `backend/app/services/front_auth_service.py` | Front CRM OAuth |
| `backend/app/services/gmail_sync_service.py` | Gmail email sync |
| `backend/app/services/outlook_sync_service.py` | Outlook email sync |
| `backend/app/services/zoom_sync_service.py` | Zoom recording sync |
| `backend/app/services/auto_sync_service.py` | APScheduler sync triggers |

### Models (29 total)
| Model | Key Fields |
|-------|-----------|
| User | clerk_id (unique), email, first_name, last_name |
| Organization | slug (unique), org_type, max_members |
| OrganizationMember | org_id + user_id (unique), role, is_active |
| Client | org_id, owner_id, is_tax_preparer, consent_status |
| Document | client_id, external_id, source, processed, is_superseded |
| DocumentChunk | document_id, client_id, chunk_text, embedding (Vector 1536) |
| DocumentPageImage | document_id, page_number, image_path |
| ClientConsent | client_id, consent_type, signing_token (unique) |
| UserSubscription | user_id (unique), org_id, tier, stripe_status |
| IntegrationConnection | user_id + provider + email (unique) |
| TokenUsage | user_id, org_id, model, prompt_tokens, estimated_cost_usd |
| ActionItem | document_id, client_id, status, priority, due_date |
| ChatMessage | client_id, role, content, sources (JSONB) |
| ProcessedWebhookEvent | id (Stripe event ID, PK) |
