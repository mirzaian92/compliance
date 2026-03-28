from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.db import connect, init_db


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    # Each test can freely mutate environment variables.
    get_settings.cache_clear()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path):
    c = connect(str(db_path))
    init_db(c)
    return c


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("DIGEST_TIMEZONE", "UTC")
    monkeypatch.setenv("DIGEST_HOUR", "7")
    monkeypatch.setenv("DIGEST_MINUTE", "0")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("HTTP_RETRIES", "0")
