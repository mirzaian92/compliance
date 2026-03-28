from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests import HTTPError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings


log = logging.getLogger(__name__)


RESEND_EMAILS_ENDPOINT = "https://api.resend.com/emails"


@dataclass(frozen=True)
class EmailSendResult:
    message_id: str | None
    response_json: dict[str, Any] | None
    already_sent: bool = False


def parse_recipients(email_to: str) -> list[str]:
    parts = [p.strip() for p in (email_to or "").split(",")]
    return [p for p in parts if p]


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=max(1, settings.http_retries),
        backoff_factor=settings.http_backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


class ResendEmailer:
    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.resend_api_key:
            raise RuntimeError("RESEND_API_KEY is required to send email")
        if not settings.email_from:
            raise RuntimeError("EMAIL_FROM is required to send email")
        if not settings.email_to:
            raise RuntimeError("EMAIL_TO is required to send email")
        self.session = _session(settings)

    def send_digest(
        self,
        *,
        subject: str,
        html_body: str,
        text_body: str,
        idempotency_key: str | None = None,
    ) -> EmailSendResult:
        to_list = parse_recipients(self.settings.email_to or "")
        if not to_list:
            raise RuntimeError("EMAIL_TO must include at least one recipient")

        headers = {
            "Authorization": f"Bearer {self.settings.resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.settings.user_agent,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        payload = {
            "from": self.settings.email_from,
            "to": to_list,
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }

        log.info("Sending email via Resend to=%s subject=%s", ",".join(to_list), subject)
        resp = self.session.post(
            RESEND_EMAILS_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=self.settings.http_timeout_seconds,
        )

        if resp.status_code == 409:
            # Resend idempotency errors:
            # - concurrent_idempotent_requests: safe to retry
            # - invalid_idempotent_request: same key, different payload
            data409 = resp.json() if resp.content else None
            err_type = None
            if isinstance(data409, dict):
                err_type = data409.get("type") or data409.get("error", {}).get("type")
            if err_type == "concurrent_idempotent_requests":
                time.sleep(2)
                resp = self.session.post(
                    RESEND_EMAILS_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=self.settings.http_timeout_seconds,
                )
            elif err_type == "invalid_idempotent_request":
                # Most likely: the same Idempotency-Key was used earlier (e.g., prior success but DB didn't record it).
                log.warning("Resend idempotency conflict; treating as already sent key=%s", idempotency_key)
                return EmailSendResult(message_id=None, response_json=data409 if isinstance(data409, dict) else None, already_sent=True)
            else:
                resp.raise_for_status()

        def _parse_body(r: requests.Response) -> dict[str, Any] | None:
            try:
                if not r.content:
                    return None
                data_any = r.json()
                return data_any if isinstance(data_any, dict) else {"raw": data_any}
            except Exception:
                text = (r.text or "").strip()
                return {"raw_text": text[:2000]} if text else None

        try:
            resp.raise_for_status()
        except HTTPError as e:
            body = _parse_body(resp)
            log.error("Resend error status=%s body=%s", resp.status_code, json.dumps(body)[:2000] if body else None)
            hint = ""
            if resp.status_code == 403:
                hint = " (403 Forbidden: check RESEND_API_KEY and that EMAIL_FROM is a verified sender/domain in Resend)"
            raise RuntimeError(f"Resend send failed: HTTP {resp.status_code}{hint}") from e

        data = _parse_body(resp)
        message_id = None
        if isinstance(data, dict):
            message_id = data.get("id") if isinstance(data.get("id"), str) else None
        log.info("Resend response message_id=%s meta=%s", message_id, json.dumps(data)[:1000] if data else None)
        return EmailSendResult(message_id=message_id, response_json=data if isinstance(data, dict) else None, already_sent=False)
