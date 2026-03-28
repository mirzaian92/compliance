import pytest

from app.models import AIClassificationResult, JurisdictionLevel, RiskLevel, StatusLabel, UpdateCategory


def test_ai_schema_parses_valid_payload() -> None:
    payload = {
        "is_relevant": True,
        "jurisdiction_level": "federal",
        "jurisdiction_name": "United States",
        "state_code": None,
        "category": "agency_notice",
        "products": ["hemp", "THCA"],
        "risk_level": "medium",
        "action_needed": False,
        "short_summary": "FDA issued an agency notice related to hemp-derived products.",
        "why_it_matters": "This may affect labeling and marketing claims for covered products.",
        "effective_date": None,
        "status_label": "notice",
        "confidence": 0.72,
    }
    res = AIClassificationResult.model_validate(payload)
    assert res.is_relevant is True
    assert res.jurisdiction_level == JurisdictionLevel.federal
    assert res.category == UpdateCategory.agency_notice
    assert res.risk_level == RiskLevel.medium
    assert res.status_label == StatusLabel.notice


def test_ai_schema_requires_state_code_for_state_items() -> None:
    payload = {
        "is_relevant": True,
        "jurisdiction_level": "state",
        "jurisdiction_name": "California",
        "state_code": None,
        "category": "bill_introduced",
        "products": ["kratom"],
        "risk_level": "low",
        "action_needed": False,
        "short_summary": "A bill was introduced.",
        "why_it_matters": "It could change rules.",
        "effective_date": None,
        "status_label": "proposed",
        "confidence": 0.4,
    }
    with pytest.raises(ValueError):
        AIClassificationResult.model_validate(payload)

