from dotenv import load_dotenv
load_dotenv()

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.action_items import router as action_items_router
from app.api.client_types import router as client_types_router
from app.api.clients import router as clients_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.integrations import router as integrations_router
from app.api.rag import router as rag_router
from app.api.briefs import router as briefs_router
from app.api.timeline import router as timeline_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Settings (read once at module load so CORS is configured synchronously) ────
_settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="AdvisoryBoard API",
    description="Client context management for CPA firms",
    version="1.0.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# cors_origins always includes localhost dev origins; production origins are
# added via the ALLOWED_ORIGINS env var (comma-separated list).
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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "AdvisoryBoard API is running"}


@app.get("/health")
async def health():
    """
    Liveness probe used by Railway and other orchestrators.

    Returns the current environment and whether TEST_MODE is active so
    operators can verify production settings at a glance.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "test_mode": settings.test_mode,
    }


# ── API routers ───────────────────────────────────────────────────────────────

app.include_router(client_types_router, prefix="/api", tags=["client-types"])
app.include_router(clients_router,      prefix="/api", tags=["clients"])
app.include_router(dashboard_router,    prefix="/api", tags=["dashboard"])
app.include_router(documents_router,    prefix="/api", tags=["documents"])
app.include_router(integrations_router, prefix="/api", tags=["integrations"])
app.include_router(rag_router,          prefix="/api", tags=["rag"])
app.include_router(action_items_router, prefix="/api", tags=["action-items"])
app.include_router(briefs_router,       prefix="/api", tags=["briefs"])
app.include_router(timeline_router,     prefix="/api", tags=["timeline"])
