from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105 - rejected in production


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "DHANZ AI"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./dhanz.db"

    jwt_secret: str = _INSECURE_DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_models: str = "gpt-4.1-mini,gpt-4.1"
    anthropic_api_key: str | None = None
    anthropic_models: str = "claude-sonnet-5-5,claude-haiku-5-5,claude-opus-5-5"
    gemini_api_key: str | None = None
    gemini_models: str = "gemini-2.5-flash,gemini-2.5-pro"
    ollama_base_url: str | None = None
    ollama_models: str = "llama3.1"

    # Web research (Phase 2). Configure one search provider; "none" disables web search
    # (Dhanz can still read links the user pastes).
    search_provider: Literal["none", "brave", "tavily", "searxng"] = "none"
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    searxng_url: str | None = None
    research_max_results: int = Field(default=6, ge=1, le=20)
    research_max_pages: int = Field(default=4, ge=1, le=10)
    fetch_user_agent: str = "DhanzAI-Research/0.2 (+https://github.com/rodsangle/videotomp3)"

    # Knowledge library embeddings; "none" falls back to keyword search.
    embedding_provider: Literal["none", "openai", "gemini", "ollama"] = "none"
    embedding_model: str | None = None
    rate_limit_ingest_per_minute: int = 20

    # Uploaded files (Phase 3). Stored on local disk under STORAGE_DIR (mount a volume in production).
    storage_dir: str = "./data/uploads"
    max_upload_mb: int = Field(default=20, ge=1, le=200)
    max_attachments_per_message: int = Field(default=5, ge=1, le=20)
    rate_limit_upload_per_minute: int = 20
    # Optional ClamAV (clamd) malware scanning. When CLAMAV_HOST is set, files that cannot be
    # scanned are rejected (fail closed); when unset, files are stored as "not_scanned".
    clamav_host: str | None = None
    clamav_port: int = 3310

    # Speech-to-text for the voice assistant: an OpenAI-compatible /audio/transcriptions endpoint
    # (OpenAI, or a self-hosted Whisper server). Text-to-speech runs on the device.
    stt_provider: Literal["none", "openai"] = "none"
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_base_url: str | None = None  # defaults to OPENAI_BASE_URL
    stt_api_key: str | None = None  # defaults to OPENAI_API_KEY
    max_audio_mb: int = Field(default=20, ge=1, le=25)

    # Push notifications (Phase 4): "your answer is ready" when a reply finishes while the app is closed.
    # Android: Firebase Cloud Messaging service-account JSON (inline or file path).
    fcm_service_account_json: str | None = None
    fcm_service_account_file: str | None = None
    # iOS: APNs token-based auth (.p8 key from the Apple Developer account).
    apns_team_id: str | None = None
    apns_key_id: str | None = None
    apns_private_key: str | None = None
    apns_private_key_file: str | None = None
    apns_bundle_id: str | None = None
    apns_use_sandbox: bool = False

    # App updates (Phase 4): JSON manifest written by the release workflow (latest.json).
    update_manifest_file: str | None = None

    # Assistant tools (calculator, units, dates, reminders, email drafts) for models that support them.
    assistant_tools_enabled: bool = True
    reminder_check_seconds: int = Field(default=30, ge=5, le=3600)

    # ---- Production readiness (Phase 5) ----
    log_format: Literal["text", "json"] = "text"
    # Prometheus metrics at GET /metrics, only when a token is set (send it as a Bearer token).
    metrics_token: str | None = None
    # Shared rate limits across API replicas; without it each process counts on its own.
    redis_url: str | None = None
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    # JSON request bodies above this size are refused (uploads have MAX_UPLOAD_MB / MAX_AUDIO_MB).
    max_request_kb: int = Field(default=512, ge=16, le=10_240)
    # Set to false for a private server: only the very first account (the admin) can register.
    allow_registration: bool = True
    # Per-account protection against password guessing (on top of the per-IP limit).
    login_lockout_attempts: int = Field(default=5, ge=1, le=100)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    # Password reset by email (a one-time code typed into the app). Disabled without SMTP_HOST.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    # Email verification (needs SMTP). New accounts get a 6-digit code by email. With
    # REQUIRE_EMAIL_VERIFICATION=true, chats, files and the library stay locked until it is entered.
    require_email_verification: bool = False
    email_verification_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    # Encrypts two-factor secrets at rest. Falls back to JWT_SECRET; set it separately so rotating
    # JWT_SECRET does not lock out everyone who uses an authenticator app.
    data_encryption_key: str | None = None
    # Time to type the authenticator code after the password was accepted.
    mfa_challenge_minutes: int = Field(default=5, ge=1, le=30)
    # Sign in with Google / Apple: the OAuth client IDs whose ID tokens are accepted (comma-separated).
    # GOOGLE_CLIENT_IDS: the first one is the "Web application" client the apps request tokens for.
    # APPLE_CLIENT_IDS: the iOS/macOS bundle ID (ai.dhanz.app) and/or a Services ID.
    google_client_ids: str = ""
    apple_client_ids: str = ""
    # Privacy & maintenance: background clean-up job.
    maintenance_interval_minutes: int = Field(default=60, ge=0, le=1440)  # 0 = off
    audit_log_retention_days: int = Field(default=365, ge=7, le=3650)
    temporary_chat_hours: int = Field(default=24, ge=1, le=720)

    default_routing_policy: Literal["balanced", "cheapest", "best", "local_first"] = "balanced"
    default_temperature: float = 0.7
    default_max_tokens: int = Field(default=2048, ge=64, le=32000)

    max_message_chars: int = 32_000
    history_max_messages: int = 40
    rate_limit_auth_per_minute: int = 10
    rate_limit_chat_per_minute: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return _csv(self.cors_origins)

    @property
    def google_client_id_list(self) -> list[str]:
        return _csv(self.google_client_ids)

    @property
    def apple_client_id_list(self) -> list[str]:
        return _csv(self.apple_client_ids)

    @property
    def openai_model_list(self) -> list[str]:
        return _csv(self.openai_models)

    @property
    def anthropic_model_list(self) -> list[str]:
        return _csv(self.anthropic_models)

    @property
    def gemini_model_list(self) -> list[str]:
        return _csv(self.gemini_models)

    @property
    def ollama_model_list(self) -> list[str]:
        return _csv(self.ollama_models)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Settings:
        if not self.jwt_secret and self.app_env != "production":
            self.jwt_secret = _INSECURE_DEV_SECRET  # blank JWT_SECRET= line in a dev .env
        if self.app_env == "production":
            if self.jwt_secret == _INSECURE_DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Use PostgreSQL (DATABASE_URL=postgresql+asyncpg://...) in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
