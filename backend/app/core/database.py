from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


def _build_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,   # detect stale connections
        pool_size=5,
        max_overflow=10,
    )


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    Yield a SQLAlchemy session and close it when the request finishes.

    Usage:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schema initialisation (dev / testing)
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create all tables that are registered with Base.metadata.

    Models are imported here (not at module level) to avoid circular imports.
    Prefer Alembic migrations in production; use this for tests or a quick
    first-run setup.
    """
    # Importing registers the models' metadata with Base before create_all().
    import app.models.user          # noqa: F401
    import app.models.client        # noqa: F401
    import app.models.document      # noqa: F401
    import app.models.document_chunk  # noqa: F401
    import app.models.interaction   # noqa: F401

    Base.metadata.create_all(bind=engine)
