from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings
from app.models import JurisdictionLevel, RawDocumentCandidate, utc_now


log = logging.getLogger(__name__)


LEGISCAN_ENDPOINT = "https://api.legiscan.com/"


US_STATE_CODES: list[str] = [
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
]


class LegiScanClient:
    def __init__(self, api_key: str, settings: Settings):
        self.api_key = api_key
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        retry = Retry(
            total=settings.http_retries,
            backoff_factor=settings.http_backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def get(self, op: str, **params: Any) -> dict[str, Any]:
        merged = {"key": self.api_key, "op": op}
        merged.update(params)
        resp = self.session.get(
            LEGISCAN_ENDPOINT, params=merged, timeout=self.settings.http_timeout_seconds
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            raise RuntimeError(f"LegiScan error: {data!r}")
        return data

    def search(self, state: str, query: str, page: int = 1) -> dict[str, Any]:
        return self.get("search", state=state, query=query, page=page)


def parse_search_results(
    state_code: str,
    payload: dict[str, Any],
    fetched_at: datetime,
    cutoff_dt: datetime | None = None,
) -> list[RawDocumentCandidate]:
    sr = payload.get("searchresult") or {}
    out: list[RawDocumentCandidate] = []

    for k, v in sr.items():
        if not isinstance(k, str) or not k.isdigit():
            continue
        if not isinstance(v, dict):
            continue

        title = (v.get("title") or v.get("bill_title") or "").strip()
        url = (v.get("state_link") or v.get("url") or "").strip()
        desc = (v.get("description") or v.get("summary") or "").strip()
        last_action = (v.get("last_action") or "").strip()
        last_action_date = (v.get("last_action_date") or v.get("status_date") or "").strip()

        published_at = fetched_at
        if last_action_date:
            try:
                published_at = datetime.fromisoformat(last_action_date).replace(tzinfo=timezone.utc)
            except ValueError:
                published_at = fetched_at

        if cutoff_dt is not None and published_at < cutoff_dt:
            continue

        if not title or not url:
            continue

        raw_text = " ".join([p for p in [desc, f"Last action: {last_action}" if last_action else ""] if p]).strip()
        if not raw_text:
            raw_text = title

        out.append(
            RawDocumentCandidate(
                source_name="legiscan",
                jurisdiction_level=JurisdictionLevel.state,
                jurisdiction_name=state_code,
                state_code=state_code,
                title=title,
                url=url,
                published_at=published_at,
                raw_text=raw_text,
                fetched_at=fetched_at,
            )
        )

    return out


def build_queries() -> list[str]:
    return [
        "hemp",
        "THCA",
        "kratom",
        "7-hydroxymitragynine",
        "psilocybin",
        "muscimol",
        "amanita",
        "MGM-15",
    ]


def fetch_state(client: LegiScanClient, state_code: str, max_pages: int = 1) -> list[RawDocumentCandidate]:
    fetched_at = utc_now()
    cutoff_dt = utc_now() - timedelta(days=client.settings.legiscan_days_back)
    out: list[RawDocumentCandidate] = []
    for q in build_queries():
        for page in range(1, max_pages + 1):
            log.info("LegiScan search state=%s query=%s page=%s", state_code, q, page)
            payload = client.search(state=state_code, query=q, page=page)
            out.extend(parse_search_results(state_code, payload, fetched_at=fetched_at, cutoff_dt=cutoff_dt))
            if client.settings.legiscan_request_delay_seconds:
                time.sleep(client.settings.legiscan_request_delay_seconds)
    deduped: list[RawDocumentCandidate] = []
    seen = set()
    for d in out:
        u = str(d.url)
        if u in seen:
            continue
        seen.add(u)
        deduped.append(d)
    return deduped


def fetch_all_states(settings: Settings, states: Iterable[str] | None = None) -> list[RawDocumentCandidate]:
    if not settings.legiscan_api_key:
        raise RuntimeError("LEGISCAN_API_KEY is required for LegiScan fetching")
    client = LegiScanClient(settings.legiscan_api_key, settings)
    out: list[RawDocumentCandidate] = []
    for st in (list(states) if states is not None else US_STATE_CODES):
        try:
            out.extend(fetch_state(client, st))
        except Exception as e:
            log.warning("LegiScan state fetch failed state=%s error=%s", st, e)
    return out
