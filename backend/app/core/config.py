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
    anthropic_api_key: str = ""

    # ── Clerk ─────────────────────────────────────────────────────────────────
    clerk_frontend_api_url: str = ""   # e.g. https://your-app.clerk.accounts.dev
    clerk_secret_key: str = ""         # sk_test_... (for server-side Clerk API calls)

    # ── Admin ──────────────────────────────────────────────────────────────────
    admin_user_id: str | None = None   # Clerk user ID for admin access (ADMIN_USER_ID)
    admin_api_key: str | None = None   # Long-lived API key for local admin dashboard

    # ── Testing ───────────────────────────────────────────────────────────────
    # When True, accept clerk_secret_key as a bearer token (dev only).
    # Automatically forced to False when ENVIRONMENT=production.
    test_mode: bool = False

    # ── Supabase ────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_service_key: str = ""

    # ── Google OAuth ─────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/integrations/google/callback"

    # ── Microsoft OAuth ───────────────────────────────────────────────────
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/api/integrations/microsoft/callback"

    # ── Zoom OAuth ─────────────────────────────────────────────────────────
    zoom_client_id: str = ""
    zoom_client_secret: str = ""
    zoom_redirect_uri: str = "http://localhost:8000/api/integrations/zoom/callback"

    # ── Front OAuth ────────────────────────────────────────────────────────
    front_client_id: str = ""
    front_client_secret: str = ""
    front_redirect_uri: str = "http://localhost:8000/api/integrations/front/callback"

    # ── Google AI ───────────────────────────────────────────────────────────
    google_ai_api_key: str = ""

    # ── Stripe ──────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_professional: str = ""
    stripe_price_firm: str = ""
    stripe_price_starter_annual: str = ""
    stripe_price_professional_annual: str = ""
    stripe_price_firm_annual: str = ""

    # Firm hybrid pricing (base + add-on seats)
    stripe_price_firm_hybrid_monthly: str = ""
    stripe_price_firm_hybrid_annual: str = ""
    stripe_price_addon_seat_monthly: str = ""
    stripe_price_addon_seat_annual: str = ""

    # ── Slack ──────────────────────────────────────────────────────────────
    slack_webhook_url: str | None = None

    # ── Resend (transactional email) ─────────────────────────────────────
    resend_api_key: str | None = None
    resend_from_email: str | None = None

    # ── Encryption ───────────────────────────────────────────────────────────
    encryption_key: str = ""

    # ── Auto-sync ──────────────────────────────────────────────────────────
    auto_sync_enabled: bool = True

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, e.g.:
    #   ALLOWED_ORIGINS=https://yourapp.railway.app,https://yourapp.com
    # The localhost dev origins are always included automatically.
    allowed_origins: str = ""

    # ── Browser extension ─────────────────────────────────────────────────
    # Stable Chrome extension origin, e.g. "chrome-extension://abcdefghijklmnop"
    # Set after the extension is published to the Chrome Web Store.
    extension_origin: str = ""

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
    def cors_origins(self) -> list[str]:
        """
        Combined CORS origin list.

        In development: includes localhost dev origins + any chrome-extension origin.
        In production: only origins from ALLOWED_ORIGINS env var + EXTENSION_ORIGIN.
        """
        extra = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

        # Add the stable extension origin if configured
        if self.extension_origin:
            extra.append(self.extension_origin)

        if self.environment == "production":
            return extra

        dev = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"]
        seen: set[str] = set()
        result: list[str] = []
        for origin in dev + extra:
            if origin not in seen:
                seen.add(origin)
                result.append(origin)
        return result

    @property
    def cors_allow_origin_regex(self) -> str | None:
        """
        In development, allow any chrome-extension:// origin for local testing.
        In production, return None (only exact origins are used).
        """
        if self.environment != "production":
            return r"^chrome-extension://.*$"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
