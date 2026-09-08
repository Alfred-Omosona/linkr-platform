"""Configuration — everything comes from the environment, nothing is hardcoded.

All variables use the `LINKR_` prefix so they can't collide with anything else on
the host. Defaults here are LOCAL-DEV defaults only; every environment (staging,
prod) is expected to override them.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LINKR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- required in every real environment -------------------------------
    database_url: str = "postgresql+psycopg://linkr:linkr@localhost:5432/linkr"

    # Public base used to build the short links we hand back to callers.
    # In staging this must be the public URL of the service, not localhost.
    base_url: str = "http://localhost:8000"

    # --- operational ------------------------------------------------------
    env: str = "local"          # local | staging | prod — surfaced on /health
    version: str = "0.1.0"      # set by the build, not by hand
    git_sha: str = "unknown"    # set by the build so we can tell what's deployed
    log_level: str = "info"

    # Comma-separated list, or "*" for any origin.
    cors_origins: str = "*"

    # --- tuning -----------------------------------------------------------
    code_length: int = 7
    db_pool_size: int = 5
    db_max_overflow: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
