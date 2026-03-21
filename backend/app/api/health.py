from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    """Detailed health check with dependency status for uptime monitoring."""
    checks: dict[str, bool] = {}

    # Database check — run a simple query
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    finally:
        try:
            db.close()
        except Exception:
            pass

    # Supabase storage check — verify config is present
    settings = get_settings()
    checks["supabase_storage"] = bool(settings.supabase_url)

    all_healthy = all(checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "checks": checks,
    }


@router.get("/ping")
async def ping():
    """Minimal liveness probe."""
    return {"pong": True}
