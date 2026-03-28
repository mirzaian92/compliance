from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from app.models import NormalizedUpdateRecord, PRODUCT_KEYWORDS, REGULATORY_KEYWORDS


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DASHES_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_WS_RE = re.compile(r"\s+")


def normalize_for_matching(text: str) -> str:
    t = text.lower()
    t = _DASHES_RE.sub("-", t)
    t = t.replace("_", " ")
    t = _WS_RE.sub(" ", t)
    return t.strip()


def tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalize_for_matching(text)))


def _keyword_variants(keyword: str) -> list[str]:
    k = normalize_for_matching(keyword)
    variants = {k}
    variants.add(k.replace("-", " "))
    variants.add(k.replace(" ", "-"))
    variants.add(k.replace("-", ""))
    variants.add(k.replace(" ", ""))
    return [v for v in variants if v]


def match_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    normalized_text = normalize_for_matching(text)
    tokens = tokenize(normalized_text)
    matches: list[str] = []
    seen = set()

    for kw in keywords:
        canonical = kw
        found = False
        for v in _keyword_variants(kw):
            # For multi-word and hyphenated forms, substring matching is more reliable than tokenization.
            if " " in v or "-" in v:
                if v in normalized_text:
                    found = True
                    break
            else:
                if v in tokens:
                    found = True
                    break
                # Allow short tokens but avoid substring false positives (e.g., "thc" inside "thca").
                if len(v) <= 4:
                    if re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", normalized_text):
                        found = True
                        break
        if found and canonical not in seen:
            seen.add(canonical)
            matches.append(canonical)

    return matches


def infer_topic(product_matches: list[str]) -> str:
    text = " ".join(product_matches).lower()
    if any(k in text for k in ["kratom", "mitragynine", "7-hydroxymitragynine", "7-oh", "7oh"]):
        return "kratom"
    if any(k in text for k in ["psilocybin", "psilocin", "mushroom", "amanita", "muscimol", "ibotenic acid"]):
        return "mushrooms"
    if any(k in text for k in ["mgm-15", "mgm15"]):
        return "mgm-15"
    if any(k in text for k in ["hemp", "cbd", "thc", "thca", "delta-8", "delta 8", "delta-9", "delta 9"]):
        return "hemp/cannabinoids"
    return "other"


def summarize_stub(title: str, product_matches: list[str], reg_matches: list[str]) -> str:
    pm = ", ".join(product_matches[:5])
    rm = ", ".join(reg_matches[:5])
    if pm and rm:
        return f"{title} (products: {pm}; signals: {rm})"
    if pm:
        return f"{title} (products: {pm})"
    return title


@dataclass(frozen=True)
class NormalizationResult:
    product_matches: list[str]
    reg_matches: list[str]
    topic: str
    is_relevant: bool
    summary_stub: str


def normalize_text(title: str, raw_text: str) -> NormalizationResult:
    combined = f"{title}\n{raw_text}"
    product_matches = match_keywords(combined, PRODUCT_KEYWORDS)
    reg_matches = match_keywords(combined, REGULATORY_KEYWORDS)
    topic = infer_topic(product_matches)

    is_relevant = len(product_matches) > 0
    summary = summarize_stub(title, product_matches, reg_matches)
    return NormalizationResult(
        product_matches=product_matches,
        reg_matches=reg_matches,
        topic=topic,
        is_relevant=is_relevant,
        summary_stub=summary,
    )


def normalize_row_to_update(raw_row: dict) -> NormalizedUpdateRecord:
    res = normalize_text(raw_row["title"], raw_row["raw_text"])
    return NormalizedUpdateRecord(
        raw_document_id=int(raw_row["id"]),
        topic=res.topic,
        product_matches=res.product_matches,
        reg_matches=res.reg_matches,
        summary_stub=res.summary_stub,
        is_relevant=res.is_relevant,
    )


def pretty_matches_json(matches_json: str) -> str:
    try:
        return ", ".join(json.loads(matches_json))
    except Exception:
        return matches_json
