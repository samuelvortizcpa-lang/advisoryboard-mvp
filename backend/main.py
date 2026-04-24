from dotenv import load_dotenv
load_dotenv(".env.local")

import logging
from logging.config import dictConfig
import os

dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "default",
        },
    },
    "loggers": {
        "rag_pipeline": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "performance": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "app": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "uvicorn.access": {"level": "INFO"},
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
})

import sentry_sdk

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

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
from app.api.rag_analytics import router as rag_analytics_router
from app.api.stripe_routes import router as stripe_router
from app.api.health import router as health_router
from app.api.consents import router as consents_router
from app.api.consent_public import router as consent_public_router
from app.api.organizations import router as organizations_router
from app.api.client_assignments import router as client_assignments_router
from app.api.strategies import router as strategies_router
from app.api.strategy_dashboard import router as strategy_dashboard_router
from app.api.audit import router as audit_router
from app.api.support import router as support_router
from app.api.communications import router as communications_router
from app.api.extension import router as extension_router
from app.api.notifications import router as notifications_router
from app.api.users import router as users_router
from app.api.context import router as context_router
from app.api.financials import router as financials_router
from app.api.journal import router as journal_router
from app.api.engagements import router as engagements_router
from app.api.practice_book import router as practice_book_router
from app.api.sessions import router as sessions_router
from app.api.contradictions import router as contradictions_router
from app.api.checkins import checkin_router, checkin_public_router
from app.api.pdf_export import router as pdf_export_router
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

_cors_kwargs: dict = dict(
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Admin-Key",
        "X-Org-Id",
        "sentry-trace",
        "baggage",
    ],
    expose_headers=["Content-Disposition"],
)
# In development, allow any chrome-extension:// origin for local extension testing
if _settings.cors_allow_origin_regex:
    _cors_kwargs["allow_origin_regex"] = _settings.cors_allow_origin_regex

app.add_middleware(CORSMiddleware, **_cors_kwargs)


# ── Security response headers ────────────────────────────────────────────────
# Added AFTER CORSMiddleware so it executes first (Starlette LIFO order).


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ── Performance timing middleware ─────────────────────────────────────────────
import time as _time

_perf_logger = logging.getLogger("performance")


class TimingMiddleware(BaseHTTPMiddleware):
    """Log slow requests and add X-Response-Time header for debugging."""

    async def dispatch(self, request, call_next):
        start = _time.monotonic()
        response = await call_next(request)
        duration = _time.monotonic() - start

        if duration > 1.0:
            _perf_logger.warning(
                "SLOW REQUEST: %s %s took %.2fs",
                request.method, request.url.path, duration,
            )

        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        return response


app.add_middleware(TimingMiddleware)


# ── Startup log ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup_log() -> None:
    """Log key configuration flags so the first log line confirms the runtime mode."""
    settings = get_settings()
    logger.info(
        "Callwen API started | environment=%s | test_mode=%s | "
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

    # ── Deadline reminder scheduler ──────────────────────────────────────
    from app.services.deadline_reminder_service import start_deadline_scheduler
    start_deadline_scheduler()

    # ── Engagement engine scheduler ──────────────────────────────────────
    from app.services.engagement_engine import start_engagement_scheduler
    start_engagement_scheduler()

    # ── Fix stuck documents on startup ──────────────────────────────────
    try:
        from sqlalchemy import text as sa_text
        from app.core.database import SessionLocal
        db = SessionLocal()
        # 1. Image files should always be marked processed
        r1 = db.execute(sa_text(
            "UPDATE documents SET processed = true, processing_error = NULL "
            "WHERE processed = false AND ("
            "  file_type IN ('png','jpg','jpeg','gif','webp','bmp','tiff')"
            "  OR filename ILIKE '%.png' OR filename ILIKE '%.jpg'"
            "  OR filename ILIKE '%.jpeg'"
            ")"
        ))
        # 2. Any document stuck >10 min is likely a failed pipeline run
        r2 = db.execute(sa_text(
            "UPDATE documents SET processed = true, "
            "  processing_error = 'Processing timed out — document stored but not indexed for search' "
            "WHERE processed = false "
            "  AND upload_date < NOW() - INTERVAL '10 minutes'"
        ))
        db.commit()
        total = (r1.rowcount or 0) + (r2.rowcount or 0)
        if total > 0:
            logger.info("Fixed %d stuck document(s) on startup (%d image, %d timed out)",
                        total, r1.rowcount or 0, r2.rowcount or 0)
        db.close()
    except Exception as exc:
        logger.warning("Stuck document fix skipped: %s", exc)


@app.on_event("shutdown")
async def _shutdown() -> None:
    """Clean up background services on shutdown."""
    from app.services.auto_sync_service import stop_scheduler
    from app.services.background_processor import shutdown_executor
    from app.services.deadline_reminder_service import stop_deadline_scheduler
    from app.services.engagement_engine import stop_engagement_scheduler
    stop_scheduler()
    stop_deadline_scheduler()
    stop_engagement_scheduler()
    shutdown_executor()


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
app.include_router(rag_analytics_router, prefix="/api/admin/rag-analytics", tags=["rag-analytics"])
app.include_router(stripe_router,      prefix="/api/stripe", tags=["stripe"])
app.include_router(health_router,      prefix="/api", tags=["health"])
app.include_router(consents_router,   prefix="/api", tags=["consents"])
app.include_router(consent_public_router, prefix="/api/consent", tags=["consent-public"])
app.include_router(organizations_router, prefix="/api", tags=["organizations"])
app.include_router(client_assignments_router, prefix="/api", tags=["client-assignments"])
app.include_router(strategies_router,          prefix="/api", tags=["tax-strategies"])
app.include_router(strategy_dashboard_router,  prefix="/api", tags=["strategy-dashboard"])
app.include_router(audit_router,               prefix="/api", tags=["audit"])
app.include_router(support_router,             prefix="/api", tags=["support"])
app.include_router(communications_router,      prefix="/api", tags=["communications"])
app.include_router(extension_router,           prefix="/api/extension", tags=["extension"])
app.include_router(notifications_router,       prefix="/api", tags=["notifications"])
app.include_router(users_router,               prefix="/api", tags=["users"])
app.include_router(context_router,             prefix="/api", tags=["context"])
app.include_router(financials_router,          prefix="/api", tags=["financials"])
app.include_router(journal_router,             prefix="/api", tags=["journal"])
app.include_router(engagements_router,         prefix="/api", tags=["engagements"])
app.include_router(practice_book_router,       prefix="/api", tags=["practice-book"])
app.include_router(sessions_router,            prefix="/api", tags=["sessions"])
app.include_router(contradictions_router,      prefix="/api", tags=["contradictions"])
app.include_router(checkin_router,             prefix="/api", tags=["checkins"])
app.include_router(checkin_public_router,      prefix="/api/checkins/public", tags=["checkins-public"])
app.include_router(pdf_export_router,          prefix="/api", tags=["pdf-export"])
