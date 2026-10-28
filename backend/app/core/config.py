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
