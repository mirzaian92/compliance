from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings
from app.models import JurisdictionLevel, RawDocumentCandidate, utc_now


log = logging.getLogger(__name__)


FDA_FEEDS_DEFAULT: list[str] = [
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/warning-letters",
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls-market-withdrawals-safety-alerts",
]


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


def _parse_feed(content: bytes, fetched_at: datetime) -> list[RawDocumentCandidate]:
    feed = feedparser.parse(content)
    out: list[RawDocumentCandidate] = []
    for e in feed.entries:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        summary_html = e.get("summary") or e.get("description") or ""
        summary_text = BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True)
        published_at = fetched_at
        try:
            if e.get("published_parsed"):
                published_at = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
            elif e.get("updated_parsed"):
                published_at = datetime(*e.updated_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            published_at = fetched_at

        if not title or not link:
            continue

        out.append(
            RawDocumentCandidate(
                source_name="fda",
                jurisdiction_level=JurisdictionLevel.federal,
                jurisdiction_name="United States",
                title=title,
                url=link,
                published_at=published_at,
                raw_text=summary_text or title,
                fetched_at=fetched_at,
            )
        )
    return out


def parse_search_html(html: str, fetched_at: datetime) -> list[RawDocumentCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    candidates: list[tuple[str, str]] = []
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not text:
            continue
        if href.startswith("/"):
            href = "https://www.fda.gov" + href
        if not href.startswith("https://www.fda.gov/"):
            continue
        if any(
            p in href
            for p in [
                "/warning-letters/",
                "/recalls-",
                "/market-withdrawals-safety-alerts/",
                "/inspections-compliance-enforcement-and-criminal-investigations/",
            ]
        ):
            candidates.append((text, href))

    out: list[RawDocumentCandidate] = []
    seen = set()
    for title, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        out.append(
            RawDocumentCandidate(
                source_name="fda",
                jurisdiction_level=JurisdictionLevel.federal,
                jurisdiction_name="United States",
                title=title,
                url=url,
                published_at=fetched_at,
                raw_text=title,
                fetched_at=fetched_at,
            )
        )
    return out


def build_queries() -> list[str]:
    products = [
        "hemp",
        "THCA",
        "delta-8",
        "delta-9",
        "kratom",
        "mitragynine",
        "7-hydroxymitragynine",
        "muscimol",
        "amanita",
        "psilocybin",
        "psilocin",
        "MGM-15",
    ]
    actions = ["warning letter", "recall", "enforcement", "seizure", "injunction"]
    return [f"\"{a}\" {p}" for a in actions for p in products]


def fetch(settings: Settings, feeds: Iterable[str] | None = None, max_search_queries: int = 10) -> list[RawDocumentCandidate]:
    s = _session(settings)
    fetched_at = utc_now()
    out: list[RawDocumentCandidate] = []

    for feed_url in (list(feeds) if feeds is not None else FDA_FEEDS_DEFAULT):
        try:
            log.info("FDA feed fetch url=%s", feed_url)
            resp = s.get(feed_url, timeout=settings.http_timeout_seconds)
            if resp.status_code >= 400:
                continue
            out.extend(_parse_feed(resp.content, fetched_at=fetched_at))
        except Exception:
            continue

    base_search = "https://www.fda.gov/search"
    for q in build_queries()[:max_search_queries]:
        try:
            log.info("FDA search query=%s", q)
            resp = s.get(base_search, params={"s": q}, timeout=settings.http_timeout_seconds)
            if resp.status_code >= 400:
                continue
            out.extend(parse_search_html(resp.text, fetched_at=fetched_at))
        except Exception:
            continue

    deduped: list[RawDocumentCandidate] = []
    seen = set()
    for d in out:
        u = str(d.url)
        if u in seen:
            continue
        seen.add(u)
        deduped.append(d)
    return deduped

