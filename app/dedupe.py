from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from app.models import RawDocumentCandidate


_WS_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    return _WS_RE.sub(" ", text.strip())


def normalize_title(title: str) -> str:
    return normalize_whitespace(title).lower()


def normalize_url(url: str) -> str:
    u = url.strip()
    while u.endswith("/"):
        u = u[:-1]
    return u


def stable_published_date(published_at: datetime) -> str:
    dt = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    return dt.date().isoformat()


def text_hash(raw_text: str) -> str:
    canonical = normalize_whitespace(raw_text).lower().encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def dedupe_hash(title: str, url: str, published_at: datetime, raw_text: str) -> str:
    key = "|".join(
        [
            normalize_title(title),
            normalize_url(url),
            stable_published_date(published_at),
            text_hash(raw_text),
        ]
    ).encode("utf-8")
    return hashlib.sha256(key).hexdigest()


def candidate_hash(candidate: RawDocumentCandidate) -> str:
    return dedupe_hash(candidate.title, str(candidate.url), candidate.published_at, candidate.raw_text)

