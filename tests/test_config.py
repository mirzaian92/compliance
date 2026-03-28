import pytest

from app.config import get_settings


def test_settings_validate_timezone(base_env, monkeypatch) -> None:
    monkeypatch.setenv("DIGEST_TIMEZONE", "America/Los_Angeles")
    s = get_settings()
    assert s.digest_timezone == "America/Los_Angeles"


def test_settings_rejects_bad_digest_time(base_env, monkeypatch) -> None:
    monkeypatch.setenv("DIGEST_HOUR", "25")
    with pytest.raises(ValueError):
        get_settings()


def test_settings_email_required_validation(base_env, monkeypatch) -> None:
    s = get_settings()
    with pytest.raises(ValueError):
        s.validate_email_required()


def test_empty_env_var_does_not_block_dotenv(base_env, monkeypatch, tmp_path) -> None:
    # Create a .env with a value, but set the OS env var to an empty string.
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LEGISCAN_API_KEY=abc123\n", encoding="utf-8")
    monkeypatch.setenv("LEGISCAN_API_KEY", "")
    s = get_settings()
    assert s.legiscan_api_key == "abc123"
