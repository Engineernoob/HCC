from functools import lru_cache
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5433/hirectl"
    database_sync_url: str = "postgresql://postgres:password@localhost:5433/hirectl"
    sql_echo: bool = False
    db_pool_size: int = 4
    db_max_overflow: int = 4
    db_pool_timeout_seconds: int = 15
    db_pool_recycle_seconds: int = 1800

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── AI ────────────────────────────────────────────────
    ai_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    ai_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_timeout_seconds: float = 8.0
    ai_failure_cooldown_seconds: int = 120
    ai_brief_refresh_min_score: float = 65.0
    ai_brief_refresh_max_age_hours: int = 24
    ai_brief_refresh_batch_size: int = 8

    # ── GitHub ────────────────────────────────────────────
    github_token: str = ""

    # ── Email ─────────────────────────────────────────────
    resend_api_key: str = ""
    alert_email_from: str = "hirectl@localhost"
    alert_email_to: str = ""

    # ── Data sources ──────────────────────────────────────
    crunchbase_api_key: str = ""
    sec_user_agent: str = ""
    sec_form_d_enabled: bool = True
    yc_jobs_enabled: bool = True
    wellfound_enabled: bool = True
    social_enabled: bool = True
    automation_enabled: bool = True
    career_page_renderer: Literal["auto", "http", "playwright"] = "http"
    playwright_timeout_ms: int = 15000
    http_timeout_seconds: float = 20.0
    http_max_connections: int = 20
    http_max_keepalive_connections: int = 10
    job_board_batch_size: int = 4
    career_page_batch_size: int = 3
    career_page_batch_delay_seconds: float = 1.0

    # ── App ───────────────────────────────────────────────
    log_level: str = "INFO"
    apscheduler_log_level: str = "WARNING"
    environment: Literal["development", "production"] = "development"
    scheduler_timezone: str = "America/Chicago"
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001"
    frontend_origin_regex: str = ""
    automation_watchlist_min_score: float = 72.0
    automation_watchlist_min_signals_30d: int = 1
    automation_watchlist_min_roles: int = 1
    automation_outreach_min_score: float = 84.0
    automation_outreach_follow_up_days: int = 3
    automation_outreach_contact_role: str = "engineering lead"
    automation_stale_watchlist_days: int = 14
    automation_stale_watchlist_max_score: float = 60.0
    automation_stale_watchlist_max_signals_30d: int = 0
    automation_stale_watchlist_max_roles: int = 0
    model_artifact_path: str = "artifacts/models/hiring_velocity_baseline.pkl"
    model_score_weight: float = Field(0.25, ge=0.0, le=1.0)

    # ── Score weights ─────────────────────────────────────
    score_weight_fit: float = Field(0.60, ge=0.0, le=1.0)
    score_weight_urgency: float = Field(0.40, ge=0.0, le=1.0)

    # ── Cron ──────────────────────────────────────────────
    cron_job_boards: str = "0 */4 * * *"
    cron_funding: str = "*/30 * * * *"
    cron_github: str = "0 * * * *"
    cron_social: str = "*/30 * * * *"
    cron_career_pages: str = "0 */6 * * *"
    cron_automation: str = "20 * * * *"
    cron_daily_rollups: str = "15 1 * * *"
    cron_model_refresh: str = "35 1 * * *"
    cron_brief_refresh: str = "*/20 * * * *"
    cron_daily_digest: str = "0 7 * * *"
    scheduler_run_on_startup: bool = False
    scheduler_job_max_instances: int = 1
    scheduler_job_coalesce: bool = True
    scheduler_job_misfire_grace_seconds: int = 300

    @field_validator("score_weight_fit", "score_weight_urgency", "model_score_weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Weight must be between 0 and 1")
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_database_url(cls, v: str) -> str:
        """Render exposes postgresql:// URLs; async SQLAlchemy needs asyncpg."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            v = "postgresql://" + v.removeprefix("postgres://")
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v.removeprefix("postgresql://")
        return v

    @field_validator("database_sync_url", mode="before")
    @classmethod
    def normalize_sync_database_url(cls, v: str) -> str:
        """Keep sync DB URLs compatible with psycopg2-based SQLAlchemy."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgresql+asyncpg://"):
            return "postgresql://" + v.removeprefix("postgresql+asyncpg://")
        if v.startswith("postgres://"):
            return "postgresql://" + v.removeprefix("postgres://")
        return v

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def ai_available(self) -> bool:
        if self.ai_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.ai_provider == "openai":
            return bool(self.openai_api_key)
        return bool(self.ollama_base_url.strip())

    @property
    def github_available(self) -> bool:
        return bool(self.github_token)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        candidate = self.frontend_origin_regex.strip()
        return candidate or None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
