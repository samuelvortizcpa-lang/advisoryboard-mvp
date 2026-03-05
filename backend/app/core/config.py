from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = "development"
    secret_key: str = ""
    frontend_url: str = "http://localhost:3000"

    # Deployment environment — set ENVIRONMENT=production in Railway.
    # When "production", TEST_MODE is forced to False regardless of .env.
    environment: str = "development"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = ""

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = ""

    # ── Clerk ─────────────────────────────────────────────────────────────────
    clerk_frontend_api_url: str = ""   # e.g. https://your-app.clerk.accounts.dev
    clerk_secret_key: str = ""         # sk_test_... (for server-side Clerk API calls)

    # ── Testing ───────────────────────────────────────────────────────────────
    # When True, accept clerk_secret_key as a bearer token (dev only).
    # Automatically forced to False when ENVIRONMENT=production.
    test_mode: bool = False

    # ── AWS S3 file storage ───────────────────────────────────────────────────
    # All three must be set for AWS S3 to be used; otherwise falls back to
    # Railway Object Storage (if configured) or local uploads/.
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = ""

    # ── Railway Object Storage (S3-compatible) ────────────────────────────────
    # Railway auto-injects these when you attach an Object Storage service.
    # Takes priority over AWS S3 when both sets of credentials are present.
    railway_storage_access_key_id: str = ""
    railway_storage_secret_access_key: str = ""
    railway_storage_endpoint_url: str = ""    # e.g. https://….railway.app
    railway_storage_bucket_name: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, e.g.:
    #   ALLOWED_ORIGINS=https://yourapp.railway.app,https://yourapp.com
    # The localhost dev origins are always included automatically.
    allowed_origins: str = ""

    model_config = {"env_file": ".env", "case_sensitive": False}

    # ── Production safeguards ─────────────────────────────────────────────────

    @model_validator(mode="after")
    def _production_safeguards(self) -> "Settings":
        """
        When ENVIRONMENT=production, TEST_MODE is forced to False so it can
        never be accidentally enabled in production via an env file.
        """
        if self.environment == "production":
            self.test_mode = False
        return self

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def railway_storage_enabled(self) -> bool:
        """True when all Railway Object Storage credentials are provided."""
        return bool(
            self.railway_storage_access_key_id
            and self.railway_storage_secret_access_key
            and self.railway_storage_endpoint_url
            and self.railway_storage_bucket_name
        )

    @property
    def aws_storage_enabled(self) -> bool:
        """True when all AWS S3 credentials and bucket name are provided."""
        return bool(
            self.aws_access_key_id
            and self.aws_secret_access_key
            and self.s3_bucket_name
        )

    @property
    def s3_enabled(self) -> bool:
        """True when any cloud storage backend (Railway or AWS) is configured."""
        return self.railway_storage_enabled or self.aws_storage_enabled

    @property
    def cors_origins(self) -> list[str]:
        """
        Combined CORS origin list: always includes localhost dev origins plus
        any extra origins from the ALLOWED_ORIGINS env var.
        """
        dev = ["http://localhost:3000", "http://127.0.0.1:3000"]
        extra = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        seen: set[str] = set()
        result: list[str] = []
        for origin in dev + extra:
            if origin not in seen:
                seen.add(origin)
                result.append(origin)
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()
