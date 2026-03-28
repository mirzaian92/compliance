from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings
from app.models import JurisdictionLevel, RawDocumentCandidate, coerce_datetime, utc_now


log = logging.getLogger(__name__)


FR_ENDPOINT = "https://www.federalregister.gov/api/v1/documents.json"


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": settings.user_agent})
    retry = Retry(
        total=settings.http_retries,
        backoff_factor=settings.http_backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def build_query_params(settings: Settings, term: str, today: date | None = None) -> dict[str, Any]:
    if today is None:
        today = datetime.now(timezone.utc).date()
    gte = (today - timedelta(days=settings.federal_register_days_back)).isoformat()
    return {
        "order": "newest",
        "per_page": settings.federal_register_per_page,
        "conditions[publication_date][gte]": gte,
        "conditions[term]": term,
        "fields[]": [
            "title",
            "html_url",
            "publication_date",
            "abstract",
            "agency_names",
            "type",
            "document_number",
        ],
    }


def parse_documents(payload: dict[str, Any], fetched_at: datetime | None = None) -> list[RawDocumentCandidate]:
    fetched_at = fetched_at or utc_now()
    results = payload.get("results") or []
    out: list[RawDocumentCandidate] = []
    for r in results:
        title = (r.get("title") or "").strip()
        url = r.get("html_url") or r.get("pdf_url") or ""
        pub_date = r.get("publication_date") or r.get("publication_date_dt") or ""
        published_at = coerce_datetime(pub_date)

        abstract = (r.get("abstract") or "").strip()
        agency_names = r.get("agency_names") or []
        doc_type = (r.get("type") or "").strip()
        doc_no = (r.get("document_number") or "").strip()
        raw_text = " ".join(
            [
                p
                for p in [
                    abstract,
                    f"Agencies: {', '.join(agency_names)}" if agency_names else "",
                    f"Type: {doc_type}" if doc_type else "",
                    f"Doc#: {doc_no}" if doc_no else "",
                ]
                if p
            ]
        ).strip()

        if not title or not url or not raw_text:
            continue

        out.append(
            RawDocumentCandidate(
                source_name="federal_register",
                jurisdiction_level=JurisdictionLevel.federal,
                jurisdiction_name="United States",
                title=title,
                url=url,
                published_at=published_at,
                raw_text=raw_text,
                fetched_at=fetched_at,
            )
        )
    return out


def fetch(settings: Settings, terms: list[str] | None = None) -> list[RawDocumentCandidate]:
    terms = terms or [
        "hemp OR cannabidiol OR CBD OR THC OR THCA OR delta-8 OR delta 8 OR delta-9 OR delta 9",
        "kratom OR mitragynine OR 7-hydroxymitragynine OR 7-OH OR 7OH",
        "muscimol OR amanita OR psilocybin OR psilocin OR ibotenic acid",
        "MGM-15 OR MGM15",
    ]

    s = _session(settings)
    fetched_at = utc_now()
    all_docs: list[RawDocumentCandidate] = []
    seen_urls = set()
    for term in terms:
        log.info("Federal Register fetch term=%s", term)
        for page in range(1, settings.federal_register_max_pages + 1):
            params = build_query_params(settings, term=term)
            params["page"] = page
            resp = s.get(FR_ENDPOINT, params=params, timeout=settings.http_timeout_seconds)
            resp.raise_for_status()
            payload = resp.json()
            docs = parse_documents(payload, fetched_at=fetched_at)
            log.info("Federal Register term=%s page=%s docs=%s", term, page, len(docs))
            if not docs:
                break
            for d in docs:
                u = str(d.url)
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                all_docs.append(d)
            # Stop early if results are exhausted.
            results = payload.get("results") or []
            if isinstance(results, list) and len(results) < settings.federal_register_per_page:
                break
    return all_docs
