# gstack

- For all web browsing, use the `/browse` skill from gstack. Never use `mcp__claude-in-chrome__*` tools.
- Available skills: /office-hours, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /design-shotgun, /review, /ship, /land-and-deploy, /canary, /benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review, /setup-browser-cookies, /setup-deploy, /retro, /investigate, /document-release, /codex, /cso, /autoplan, /careful, /freeze, /guard, /unfreeze, /gstack-upgrade

---

# Project Brief — Callwen

## What It Is

Callwen is an AI-powered document intelligence platform for CPA firms. Users upload tax returns, meeting recordings, client files, and other documents, then ask natural-language questions and get source-cited answers. The platform includes a full RAG pipeline, email/calendar integrations, IRC §7216 consent tracking, tax strategy tools, and Stripe-based subscription billing.

**Domain:** `callwen.com` (previously `myadvisoryboard.space`)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 3 |
| Auth | Clerk (JWT RS256, custom proxy domain at `clerk.callwen.com`) |
| Backend | FastAPI, Python 3.13, Uvicorn |
| Database | PostgreSQL + pgvector (vector similarity search) |
| ORM / Migrations | SQLAlchemy 2.0, Alembic |
| LLM / Embeddings | OpenAI (`gpt-4o`, `text-embedding-3-small`), Anthropic, Google GenAI |
| File Storage | Supabase Storage (primary), S3 (fallback) |
| Integrations | Gmail API, Microsoft Graph (Outlook), Zoom, Front CRM |
| Payments | Stripe (starter / professional / firm tiers) |
| Monitoring | Sentry (frontend + backend) |
| Email Service | Resend |
| Background Jobs | APScheduler |
| Deployment | Railway / Heroku (backend), Vercel (frontend) |

## Repository Structure

```
advisoryboard-mvp-code/
├── frontend/                  # Next.js frontend (port 3000)
│   ├── app/                   # App Router pages
│   │   ├── dashboard/         # Main app (clients, settings, calendar, actions, strategy)
│   │   ├── sign-in/           # Clerk sign-in
│   │   ├── sign-up/           # Clerk sign-up
│   │   ├── consent/sign/      # Public consent signature page
│   │   ├── privacy/ terms/    # Legal pages
│   │   └── layout.tsx         # Root layout (Cormorant Garamond + Outfit fonts)
│   ├── components/            # React components (ui/, dashboard/, clients/, documents/, auth/)
│   ├── contexts/OrgContext.tsx # Organization switching context
│   ├── lib/api.ts             # API client (~54KB, all backend calls)
│   ├── lib/useApi.ts          # API hook
│   └── middleware.ts          # Clerk auth middleware (proxied through callwen.com)
│
├── backend/                   # FastAPI backend (port 8000)
│   ├── main.py                # App entry, router registration, CORS, lifespan
│   ├── app/
│   │   ├── api/               # Route handlers (24 routers)
│   │   ├── core/              # auth.py, config.py, database.py
│   │   ├── models/            # SQLAlchemy models (29 models)
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   └── services/          # Business logic (49+ service files)
│   ├── alembic/               # Database migrations (30+ versions)
│   └── tests/                 # pytest test files
│
├── admin-dashboard/           # DEPRECATED 2026-04-13 — replaced by frontend/app/admin/ (local safety fallback, do not add new code here)
├── docs/                      # API documentation
├── Procfile                   # Railway/Heroku process definition
└── nixpacks.toml              # Nix deployment config (Python 3.13, FFmpeg, Tesseract)
```

## Key Patterns & Conventions

### Authentication
- Clerk JWT with RS256. Backend verifies via JWKS with caching (`backend/app/core/auth.py`).
- Frontend middleware proxies Clerk requests through `callwen.com/__clerk`.
- `@require_auth` decorator protects backend routes. Optional auth available for public endpoints.
- Test mode bypass accepts `CLERK_SECRET_KEY` as bearer token.

### Frontend
- **Styling:** Tailwind utility classes + inline `style={{}}` for custom values. Do NOT use `styled-jsx` — it was tried and fails with child components / dynamic content.
- **Keyframe animations:** Use plain `<style dangerouslySetInnerHTML>` tags, never `<style jsx>`.
- **API calls:** All backend communication goes through `frontend/lib/api.ts` which exports typed factory functions per resource.
- **Organization context:** `OrgContext.tsx` manages multi-tenant org switching. Firm org is preferred; personal workspace is fallback.
- **Fonts:** Cormorant Garamond (serif, headlines) and Outfit (sans, body) loaded via `next/font/google`.
- **Dynamic rendering:** `export const dynamic = 'force-dynamic'` in root layout.

### Backend
- **Router pattern:** Each API domain has its own router file in `backend/app/api/`, registered in `main.py`.
- **Service layer:** Business logic lives in `backend/app/services/`, not in route handlers.
- **Models:** SQLAlchemy 2.0 declarative style with `Mapped[]` type annotations.
- **Schemas:** Pydantic v2 models in `backend/app/schemas/` for request validation and response serialization.
- **Multi-tenancy:** Data isolated by `org_id` and `owner_id` on most models.

### RAG Pipeline
- Document upload → text extraction (PDF/Word/MSG/OCR) → chunking → OpenAI embeddings → pgvector storage.
- Queries: embed question → cosine similarity search → top-K chunks as context → GPT-4o generates cited answer.
- Domain-specific: IRS form references, tax terminology expansion.

### IRC §7216 Consent System
- Tiered consent: tax preparers require full §7216 consent; advisory-only CPAs use AICPA acknowledgment.
- `is_tax_preparer` flag on clients determines the flow.
- Consent statuses: `not_required`, `determination_needed`, `pending`, `advisory_acknowledgment_needed`, `acknowledged`, `obtained`, `sent`, `expired`, `declined`.

### Git & Deployment
- Two remotes: `origin` (samuelvortizcpa-lang) and `vercel-deploy` (samuelvortizcpa-code).
- **Deploy command:** `make deploy` (runs lint → typecheck → test → push both remotes).
- **Pre-commit hook:** Runs `tsc --noEmit` automatically. Install with `make hooks`.
- Backend deploys via Railway (Procfile runs Alembic migrations then Uvicorn).
- Frontend deploys via Vercel.
- Health checks: backend `/health`, frontend `/api/health`.

## Deploy Configuration (configured by /setup-deploy)
- Platform: Railway (backend) + Vercel (frontend)
- Production URL: https://callwen.com
- Deploy workflow: auto-deploy on push (Railway watches main, Vercel watches vercel-deploy remote)
- Git remotes use split credentials: `origin` authenticates via SSH (`~/.ssh/id_ed25519_lang`), `vercel-deploy` authenticates via HTTPS (macOS Keychain). Pushing to `origin` uses SSH; pushing to `vercel-deploy` uses HTTPS. Do not try to unify — they are intentionally split.
- Deploy status command: `make health`
- Merge method: direct push to main
- Project type: web app (SPA frontend + API backend)
- Post-deploy health check: `curl -sf https://callwen.com/api/health && curl -sf https://advisoryboard-mvp-production.up.railway.app/health`

### Deploy pipeline
- Pre-merge: `make check` (lint + typecheck + test)
- Deploy trigger: `make push` (pushes to both origin and vercel-deploy)
- Full pipeline: `make deploy` (check + push)
- Health check: `make health`

### Testing
- Backend: `make test` (pytest, 43 unit tests, ~0.6s)
- Frontend: `make typecheck` (tsc --noEmit)
- Lint: `make lint` (next lint)
- Pre-commit hook: `make hooks` to install (runs tsc --noEmit before every commit)

## Current State

- Production app live at `callwen.com` with Clerk authentication, document upload, RAG Q&A, client management, email integrations, and Stripe billing.
- Sign-in/sign-up pages use a premium dark split-layout (`components/auth/AuthLayout.tsx`) with animated gradient orbs, feature cards, counter stats, product preview mockup, and staggered entrance animations.
- Tiered §7216 consent system implemented across backend and frontend.
- Admin dashboard exists as a separate app but is minimal.
- Test coverage is limited (a few integration tests in `backend/tests/`).

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
