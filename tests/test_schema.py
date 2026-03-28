import pytest

from app.models import JurisdictionLevel, RawDocumentCandidate


def test_raw_document_candidate_requires_state_code_for_state() -> None:
    with pytest.raises(ValueError):
        RawDocumentCandidate(
            source_name="legiscan",
            jurisdiction_level=JurisdictionLevel.state,
            jurisdiction_name="CA",
            title="A bill",
            url="https://example.com",
            published_at="2026-03-27",
            raw_text="bill text",
        )


def test_raw_document_candidate_validates_shape() -> None:
    doc = RawDocumentCandidate(
        source_name="federal_register",
        jurisdiction_level=JurisdictionLevel.federal,
        jurisdiction_name="United States",
        title="Final Rule on Hemp",
        url="https://www.federalregister.gov/d/2026-00001",
        published_at="2026-03-27",
        raw_text="final rule hemp",
    )
    assert doc.title == "Final Rule on Hemp"

