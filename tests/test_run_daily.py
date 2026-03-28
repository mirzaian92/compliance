from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.main as main_mod
from app.emailer import EmailSendResult


@dataclass(frozen=True)
class _StubEmailer:
    sent: list[str]

    def __call__(self, settings):
        return self

    def send_digest(self, *, subject: str, html_body: str, text_body: str, idempotency_key: str | None = None):
        self.sent.append(subject)
        return EmailSendResult(message_id="msg_123", response_json={"id": "msg_123"}, already_sent=False)


def test_run_daily_happy_path_sends_once(base_env, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "Acme <from@example.com>")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")

    # Avoid network and make sure at least one source "succeeds".
    def _fetch_sources(conn):
        return [
            main_mod.SourceRunResult(
                name="Federal Register",
                ok=True,
                skipped=False,
                fetched=0,
                inserted=0,
                deduped=0,
                error=None,
                duration_seconds=0.01,
            )
        ]

    monkeypatch.setattr(main_mod, "_fetch_sources", _fetch_sources)

    stub = _StubEmailer(sent=[])
    monkeypatch.setattr(main_mod, "ResendEmailer", stub)

    code1 = main_mod.run_daily_flow(dry_run=False, force_send=False)
    assert code1 == 0
    assert len(stub.sent) == 1

    # Second run should skip because it was recorded as sent.
    code2 = main_mod.run_daily_flow(dry_run=False, force_send=False)
    assert code2 == 0
    assert len(stub.sent) == 1

    # Force send should send again.
    code3 = main_mod.run_daily_flow(dry_run=False, force_send=True)
    assert code3 == 0
    assert len(stub.sent) == 2


def test_run_daily_dry_run_does_not_send(base_env, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "Acme <from@example.com>")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")

    def _fetch_sources(conn):
        return [
            main_mod.SourceRunResult(
                name="Federal Register",
                ok=True,
                skipped=False,
                fetched=0,
                inserted=0,
                deduped=0,
                error=None,
                duration_seconds=0.01,
            )
        ]

    monkeypatch.setattr(main_mod, "_fetch_sources", _fetch_sources)

    stub = _StubEmailer(sent=[])
    monkeypatch.setattr(main_mod, "ResendEmailer", stub)

    code = main_mod.run_daily_flow(dry_run=True, force_send=False)
    assert code == 0
    assert stub.sent == []


def test_run_daily_all_sources_failed_returns_nonzero(base_env, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "Acme <from@example.com>")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")

    def _fetch_sources(conn):
        return [
            main_mod.SourceRunResult(
                name="Federal Register",
                ok=False,
                skipped=False,
                fetched=0,
                inserted=0,
                deduped=0,
                error="boom",
                duration_seconds=0.01,
            ),
            main_mod.SourceRunResult(
                name="FDA",
                ok=False,
                skipped=False,
                fetched=0,
                inserted=0,
                deduped=0,
                error="boom",
                duration_seconds=0.01,
            ),
        ]

    monkeypatch.setattr(main_mod, "_fetch_sources", _fetch_sources)

    stub = _StubEmailer(sent=[])
    monkeypatch.setattr(main_mod, "ResendEmailer", stub)

    code = main_mod.run_daily_flow(dry_run=False, force_send=False)
    assert code == 1
    assert stub.sent == []
