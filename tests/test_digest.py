from app.digest import GroupedDigest, group_for_digest, render_digest
from app.models import JurisdictionLevel, RiskLevel, StatusLabel, UpdateCategory
from app.digest import DigestEntry


def _entry(
    *,
    raw_document_id: int,
    jurisdiction_level: JurisdictionLevel,
    state_code: str | None,
    category: UpdateCategory,
    risk_level: RiskLevel,
    status_label: StatusLabel,
    action_needed: bool = False,
) -> DigestEntry:
    return DigestEntry(
        raw_document_id=raw_document_id,
        jurisdiction_level=jurisdiction_level,
        jurisdiction_name="United States" if jurisdiction_level == JurisdictionLevel.federal else (state_code or "State"),
        state_code=state_code,
        category=category,
        products=["hemp"],
        risk_level=risk_level,
        action_needed=action_needed,
        short_summary="Short summary.",
        why_it_matters="Why it matters.",
        effective_date=None,
        status_label=status_label,
        confidence=0.9,
        source_url="https://example.com",
        published_at="2026-03-27T00:00:00+00:00",
        source_name="test",
        title=f"title-{raw_document_id}",
    )


def test_grouping_urgent_and_watchlist() -> None:
    entries = [
        _entry(
            raw_document_id=1,
            jurisdiction_level=JurisdictionLevel.federal,
            state_code=None,
            category=UpdateCategory.recall,
            risk_level=RiskLevel.high,
            status_label=StatusLabel.recall,
        ),
        _entry(
            raw_document_id=2,
            jurisdiction_level=JurisdictionLevel.state,
            state_code="CA",
            category=UpdateCategory.bill_introduced,
            risk_level=RiskLevel.low,
            status_label=StatusLabel.proposed,
        ),
        _entry(
            raw_document_id=3,
            jurisdiction_level=JurisdictionLevel.state,
            state_code="NY",
            category=UpdateCategory.final_rule,
            risk_level=RiskLevel.medium,
            status_label=StatusLabel.enacted,
        ),
    ]
    grouped = group_for_digest(entries)
    assert len(grouped.urgent) == 1
    assert len(grouped.watchlist) == 1
    assert len(grouped.state) == 1


def test_empty_digest_renders_no_significant_updates() -> None:
    grouped = GroupedDigest(urgent=[], federal=[], state=[], watchlist=[])
    md, html = render_digest(grouped, digest_date="2026-03-27", generated_at_iso="2026-03-27T00:00:00Z")
    assert "No Significant Updates" in md
    assert "No Significant Updates" in html

