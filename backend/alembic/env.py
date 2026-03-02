"""
Alembic environment configuration.

Key responsibilities:
  1. Load DATABASE_URL from our Pydantic settings (overrides alembic.ini placeholder).
  2. Import all ORM models so their metadata is visible to autogenerate.
  3. Run migrations in online (live DB) or offline (SQL dump) mode.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Make sure `app.*` is importable when running `alembic` from the project root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Load settings and override the database URL
# ---------------------------------------------------------------------------
from app.core.config import get_settings  # noqa: E402

settings = get_settings()
context.config.set_main_option("sqlalchemy.url", settings.database_url)

# ---------------------------------------------------------------------------
# Import Base (declarative base) and ALL models so autogenerate picks them up
# ---------------------------------------------------------------------------
from app.core.database import Base  # noqa: E402
import app.models  # noqa: F401  – triggers all model imports via __init__.py

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Logging (from alembic.ini)
# ---------------------------------------------------------------------------
if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Generate a .sql migration script without connecting to the database.
    Useful for reviewing changes or applying them manually.
    """
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,          # detect column type changes
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
