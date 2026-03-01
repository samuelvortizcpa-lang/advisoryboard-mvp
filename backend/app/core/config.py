from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    secret_key: str = ""
    frontend_url: str = "http://localhost:3000"

    # Database
    database_url: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Clerk
    clerk_frontend_api_url: str = ""   # e.g. https://your-app.clerk.accounts.dev
    clerk_secret_key: str = ""          # sk_test_... (for server-side Clerk API calls)

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    return Settings()
