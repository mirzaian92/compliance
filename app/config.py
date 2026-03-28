from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")

    db_path: str = Field(default="compliance.db", alias="DB_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    http_timeout_seconds: float = Field(default=20.0, alias="HTTP_TIMEOUT_SECONDS")
    http_retries: int = Field(default=3, alias="HTTP_RETRIES")
    http_backoff_factor: float = Field(default=0.5, alias="HTTP_BACKOFF_FACTOR")
    user_agent: str = Field(default="compliance-monitor/0.1", alias="USER_AGENT")

    federal_register_days_back: int = Field(default=3, alias="FEDERAL_REGISTER_DAYS_BACK")
    federal_register_per_page: int = Field(default=100, alias="FEDERAL_REGISTER_PER_PAGE")
    federal_register_max_pages: int = Field(default=3, alias="FEDERAL_REGISTER_MAX_PAGES")

    legiscan_api_key: str | None = Field(default=None, alias="LEGISCAN_API_KEY")
    legiscan_days_back: int = Field(default=7, alias="LEGISCAN_DAYS_BACK")
    legiscan_request_delay_seconds: float = Field(default=0.2, alias="LEGISCAN_REQUEST_DELAY_SECONDS")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1", alias="OPENAI_MODEL")

    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    email_from: str | None = Field(default=None, alias="EMAIL_FROM")
    email_to: str | None = Field(default=None, alias="EMAIL_TO")

    digest_timezone: str = Field(default="America/Los_Angeles", alias="DIGEST_TIMEZONE")
    digest_hour: int = Field(default=7, alias="DIGEST_HOUR")
    digest_minute: int = Field(default=0, alias="DIGEST_MINUTE")

    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.digest_timezone)

    def validate_basic(self) -> None:
        if not (0 <= int(self.digest_hour) <= 23):
            raise ValueError("DIGEST_HOUR must be between 0 and 23")
        if not (0 <= int(self.digest_minute) <= 59):
            raise ValueError("DIGEST_MINUTE must be between 0 and 59")
        _ = self.tzinfo()
        if self.http_timeout_seconds <= 0:
            raise ValueError("HTTP_TIMEOUT_SECONDS must be > 0")
        if self.http_retries < 0:
            raise ValueError("HTTP_RETRIES must be >= 0")
        if self.federal_register_per_page <= 0:
            raise ValueError("FEDERAL_REGISTER_PER_PAGE must be > 0")
        if self.federal_register_max_pages <= 0:
            raise ValueError("FEDERAL_REGISTER_MAX_PAGES must be > 0")
        if self.legiscan_request_delay_seconds < 0:
            raise ValueError("LEGISCAN_REQUEST_DELAY_SECONDS must be >= 0")

    def validate_email_required(self) -> None:
        missing = []
        if not self.resend_api_key:
            missing.append("RESEND_API_KEY")
        if not self.email_from:
            missing.append("EMAIL_FROM")
        if not self.email_to:
            missing.append("EMAIL_TO")
        if missing:
            raise ValueError(f"Missing required email settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    # Treat empty env vars as "unset" so they don't block local .env values.
    for k in [
        "APP_ENV",
        "LEGISCAN_API_KEY",
        "OPENAI_API_KEY",
        "RESEND_API_KEY",
        "EMAIL_FROM",
        "EMAIL_TO",
    ]:
        if os.environ.get(k) == "":
            os.environ.pop(k, None)

    # Load .env early for any non-pydantic consumers too.
    load_dotenv(".env", override=False)

    settings = Settings()
    # Optional environment-specific override file: .env.dev / .env.prod / .env.test
    env_path = Path(f".env.{settings.app_env}")
    if env_path.exists():
        load_dotenv(str(env_path), override=True)
        settings = Settings()

    settings.validate_basic()
    return settings
