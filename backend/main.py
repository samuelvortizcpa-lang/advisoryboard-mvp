from dotenv import load_dotenv
load_dotenv()

import logging
import os

import sentry_sdk

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.action_items import router as action_items_router
from app.api.alerts import router as alerts_router
from app.api.client_types import router as client_types_router
from app.api.clients import router as clients_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.integrations import router as integrations_router
from app.api.rag import router as rag_router
from app.api.briefs import router as briefs_router
from app.api.timeline import router as timeline_router
from app.api.usage import router as usage_router
from app.api.admin import router as admin_router
from app.api.stripe_routes import router as stripe_router
from app.api.health import router as health_router
from app.api.consents import router as consents_router
from app.api.consent_public import router as consent_public_router
from app.api.organizations import router as organizations_router
from app.api.client_assignments import router as client_assignments_router
from app.api.strategies import router as strategies_router
from app.api.strategy_dashboard import router as strategy_dashboard_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Sentry error monitoring ──────────────────────────────────────────────────
_sentry_dsn = os.getenv("SENTRY_DSN")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "production"),
        release=os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown"),
    )
    logger.info("Sentry initialized (environment=%s)", os.getenv("ENVIRONMENT", "production"))

# ── Settings (read once at module load so CORS is configured synchronously) ────
_settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Callwen API",
    description="Client context management for CPA firms",
    version="1.0.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# cors_origins always includes localhost dev origins; production origins are
# added via the ALLOWED_ORIGINS env var (comma-separated list).
# ── Rate limiting ─────────────────────────────────────────────────────────
from app.api.consent_public import limiter as consent_limiter
app.state.limiter = consent_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ── Startup log ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup_log() -> None:
    """Log key configuration flags so the first log line confirms the runtime mode."""
    settings = get_settings()
    logger.info(
        "AdvisoryBoard API started | environment=%s | test_mode=%s | "
        "storage=supabase | cors_origins=%s",
        settings.environment,
        settings.test_mode,
        settings.cors_origins,
    )
    if settings.test_mode:
        logger.warning(
            "⚠️  TEST_MODE enabled — secret-key bearer tokens will bypass "
            "Clerk JWT verification.  Do NOT use this setting in production."
        )

    # ── Auto-sync scheduler ──────────────────────────────────────────────
    from app.services.auto_sync_service import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
async def _shutdown() -> None:
    """Clean up background services on shutdown."""
    from app.services.auto_sync_service import stop_scheduler
    stop_scheduler()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "Callwen API is running"}


@app.get("/health")
async def health():
    """Lightweight healthcheck for Railway — no auth, no DB."""
    return {"status": "ok"}


# ── API routers ───────────────────────────────────────────────────────────────

app.include_router(client_types_router, prefix="/api", tags=["client-types"])
app.include_router(clients_router,      prefix="/api", tags=["clients"])
app.include_router(dashboard_router,    prefix="/api", tags=["dashboard"])
app.include_router(documents_router,    prefix="/api", tags=["documents"])
app.include_router(integrations_router, prefix="/api", tags=["integrations"])
app.include_router(rag_router,          prefix="/api", tags=["rag"])
app.include_router(action_items_router, prefix="/api", tags=["action-items"])
app.include_router(alerts_router,       prefix="/api", tags=["alerts"])
app.include_router(briefs_router,       prefix="/api", tags=["briefs"])
app.include_router(timeline_router,     prefix="/api", tags=["timeline"])
app.include_router(usage_router,       prefix="/api", tags=["usage"])
app.include_router(admin_router,       prefix="/api/admin", tags=["admin"])
app.include_router(stripe_router,      prefix="/api/stripe", tags=["stripe"])
app.include_router(health_router,      prefix="/api", tags=["health"])
app.include_router(consents_router,   prefix="/api", tags=["consents"])
app.include_router(consent_public_router, prefix="/api/consent", tags=["consent-public"])
app.include_router(organizations_router, prefix="/api", tags=["organizations"])
app.include_router(client_assignments_router, prefix="/api", tags=["client-assignments"])
app.include_router(strategies_router,          prefix="/api", tags=["tax-strategies"])
app.include_router(strategy_dashboard_router,  prefix="/api", tags=["strategy-dashboard"])
