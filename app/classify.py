from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.ai import OpenAIClient
from app.models import (
    AIClassificationResult,
    ClassifiedUpdateRecord,
    JurisdictionLevel,
    PRODUCT_KEYWORDS,
    REGULATORY_KEYWORDS,
    RiskLevel,
    StatusLabel,
    UpdateCategory,
)
from app.normalize import match_keywords, normalize_for_matching


log = logging.getLogger(__name__)


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _dedupe_list(items: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for x in items:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def deterministic_relevance(product_matches: list[str], reg_matches: list[str], source_name: str) -> bool:
    if not product_matches:
        return False
    # LegiScan + Federal Register are inherently regulatory; FDA sources are usually enforcement/compliance.
    if source_name in {"legiscan", "federal_register", "fda"}:
        return True
    return bool(reg_matches)


def _guess_status(title: str, raw_text: str) -> StatusLabel:
    t = normalize_for_matching(f"{title}\n{raw_text}")
    if "proposed" in t or "introduced" in t:
        return StatusLabel.proposed
    if "final rule" in t or "adopted" in t or "enacted" in t or "signed" in t:
        return StatusLabel.enacted
    if "effective" in t:
        return StatusLabel.effective
    if "warning letter" in t or "enforcement" in t or "injunction" in t:
        return StatusLabel.enforcement
    if "recall" in t:
        return StatusLabel.recall
    if "notice" in t:
        return StatusLabel.notice
    return StatusLabel.unknown


def _guess_category(title: str, raw_text: str, source_name: str) -> UpdateCategory:
    t = normalize_for_matching(f"{title}\n{raw_text}")
    if "warning letter" in t:
        return UpdateCategory.warning_letter
    if "recall" in t:
        return UpdateCategory.recall
    if any(w in t for w in ["enforcement", "injunction", "seizure", "criminal", "consent decree"]):
        return UpdateCategory.enforcement_action
    if "final rule" in t:
        return UpdateCategory.final_rule
    if "proposed rule" in t or (source_name == "federal_register" and "proposed" in t and "rule" in t):
        return UpdateCategory.proposed_rule
    if source_name == "legiscan":
        if any(w in t for w in ["introduced", "filed"]):
            return UpdateCategory.bill_introduced
        if any(w in t for w in ["passed", "enrolled", "signed"]):
            return UpdateCategory.bill_passed
        return UpdateCategory.other_regulatory_update
    if any(w in t for w in ["notice", "guidance", "policy", "agency"]):
        return UpdateCategory.agency_notice
    return UpdateCategory.other_regulatory_update


def _guess_risk(category: UpdateCategory, reg_matches: list[str]) -> RiskLevel:
    if category in {UpdateCategory.recall, UpdateCategory.warning_letter, UpdateCategory.enforcement_action}:
        return RiskLevel.high
    if category in {UpdateCategory.final_rule, UpdateCategory.bill_passed}:
        return RiskLevel.medium
    # If we detected enforcement-ish language via keyword matches, bump.
    if any(k in reg_matches for k in ["recall", "warning letter", "enforcement", "ban", "prohibited"]):
        return RiskLevel.medium
    return RiskLevel.low


def build_ai_prompt(row: dict[str, Any]) -> str:
    # Keep prompt short, source-backed, and explicitly prohibit invention.
    return (
        "Classify this item for a compliance digest. Reject if it is not clearly about regulation, law, "
        "enforcement, recalls, warning letters, restrictions/bans, or official agency action.\n\n"
        "Rules:\n"
        "- Do not invent missing facts.\n"
        "- If the status/effective date is unclear, set status_label=unknown and effective_date=null.\n"
        "- short_summary must be 1-2 sentences, factual, based only on provided text.\n"
        "- why_it_matters must be 1 sentence, factual, avoid speculation.\n\n"
        "Item:\n"
        f"- source_name: {row['source_name']}\n"
        f"- jurisdiction_level (hint): {row['jurisdiction_level']}\n"
        f"- jurisdiction_name (hint): {row['jurisdiction_name']}\n"
        f"- state_code (hint): {row.get('state_code')}\n"
        f"- title: {row['title']}\n"
        f"- url: {row['url']}\n"
        f"- published_at: {row['published_at']}\n"
        f"- extracted_text_snippet:\n{row['raw_text']}\n"
    )


@dataclass(frozen=True)
class ClassificationOutcome:
    record: ClassifiedUpdateRecord | None
    used_ai: bool
    rejected: bool
    error: str | None


def classify_row(
    row: dict[str, Any],
    *,
    ai_client: OpenAIClient | None,
) -> ClassificationOutcome:
    product_matches = _safe_json_loads(row.get("product_matches_json") or "[]") or []
    reg_matches = _safe_json_loads(row.get("reg_matches_json") or "[]") or []
    product_matches = [str(x) for x in product_matches if isinstance(x, str)]
    reg_matches = [str(x) for x in reg_matches if isinstance(x, str)]

    if not deterministic_relevance(product_matches, reg_matches, str(row.get("source_name") or "")):
        return ClassificationOutcome(record=None, used_ai=False, rejected=True, error=None)

    expected_level = JurisdictionLevel(str(row["jurisdiction_level"]))
    expected_name = str(row["jurisdiction_name"])
    expected_state = row.get("state_code")

    used_ai = False
    ai_result: AIClassificationResult | None = None
    err: str | None = None
    if ai_client is not None:
        try:
            used_ai = True
            ai_result = ai_client.classify_update(prompt=build_ai_prompt(row))
        except Exception as e:
            log.warning("AI classify failed raw_document_id=%s error=%s", row.get("raw_document_id"), e)
            err = str(e)
            ai_result = None

    if ai_result is not None and not ai_result.is_relevant:
        return ClassificationOutcome(record=None, used_ai=True, rejected=True, error=None)

    if ai_result is None:
        category = _guess_category(row["title"], row["raw_text"], str(row.get("source_name") or ""))
        status = _guess_status(row["title"], row["raw_text"])
        risk = _guess_risk(category, reg_matches)
        products = _dedupe_list(product_matches)

        record = ClassifiedUpdateRecord(
            raw_document_id=int(row["raw_document_id"]),
            jurisdiction_level=expected_level,
            jurisdiction_name=expected_name,
            state_code=str(expected_state) if expected_state else None,
            category=category,
            products=products,
            risk_level=risk,
            action_needed=risk == RiskLevel.high,
            short_summary=str(row["title"]),
            why_it_matters="AI unavailable; review the source for details.",
            effective_date=None,
            status_label=status,
            confidence=0.0,
            source_url=str(row["url"]),
        )
        return ClassificationOutcome(record=record, used_ai=False, rejected=False, error=err)

    products = _dedupe_list([p for p in ai_result.products if isinstance(p, str)] + product_matches)

    # Safety: override jurisdiction with source metadata (AI may be wrong).
    confidence = float(ai_result.confidence)
    if ai_result.jurisdiction_level != expected_level:
        confidence = min(confidence, 0.5)
    if expected_level == JurisdictionLevel.state and (ai_result.state_code or "").upper() != (expected_state or ""):
        confidence = min(confidence, 0.5)

    record = ClassifiedUpdateRecord(
        raw_document_id=int(row["raw_document_id"]),
        jurisdiction_level=expected_level,
        jurisdiction_name=expected_name,
        state_code=str(expected_state) if expected_state else None,
        category=ai_result.category,
        products=products,
        risk_level=ai_result.risk_level,
        action_needed=bool(ai_result.action_needed),
        short_summary=ai_result.short_summary,
        why_it_matters=ai_result.why_it_matters,
        effective_date=ai_result.effective_date,
        status_label=ai_result.status_label,
        confidence=confidence,
        source_url=str(row["url"]),
    )
    return ClassificationOutcome(record=record, used_ai=True, rejected=False, error=err)

