from datetime import datetime, timezone

from app.sources.fda import parse_search_html as parse_fda_html
from app.sources.federal_register import parse_documents as parse_fr
from app.sources.legiscan import parse_search_results as parse_ls


def test_federal_register_parser_output_shape() -> None:
    payload = {
        "results": [
            {
                "title": "Proposed Rule: Hemp Testing",
                "html_url": "https://www.federalregister.gov/documents/2026/03/27/2026-00001/proposed-rule-hemp-testing",
                "publication_date": "2026-03-27",
                "abstract": "This proposed rule concerns hemp testing requirements.",
                "agency_names": ["Department of Agriculture"],
                "type": "Proposed Rule",
                "document_number": "2026-00001",
            }
        ]
    }
    docs = parse_fr(payload, fetched_at=datetime(2026, 3, 27, tzinfo=timezone.utc))
    assert len(docs) == 1
    assert docs[0].source_name == "federal_register"
    assert str(docs[0].url).startswith("https://")


def test_legiscan_parser_output_shape() -> None:
    payload = {
        "status": "OK",
        "searchresult": {
            "summary": {"page": 1, "state": "CA"},
            "0": {
                "title": "An act relating to kratom",
                "state_link": "https://legiscan.com/CA/bill/AB1/2025",
                "description": "Regulates kratom products.",
                "last_action": "Introduced",
                "last_action_date": "2026-03-27",
            },
        },
    }
    docs = parse_ls("CA", payload, fetched_at=datetime(2026, 3, 27, tzinfo=timezone.utc))
    assert len(docs) == 1
    assert docs[0].state_code == "CA"
    assert docs[0].jurisdiction_level.value == "state"


def test_fda_search_html_parser_output_shape() -> None:
    html = """
    <html><body>
      <main>
        <a href="/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/foo">Warning Letter: Hemp</a>
        <a href="/recalls-market-withdrawals-safety-alerts/bar">Recall: Kratom Product</a>
      </main>
    </body></html>
    """
    docs = parse_fda_html(html, fetched_at=datetime(2026, 3, 27, tzinfo=timezone.utc))
    assert len(docs) == 2
    assert all(d.source_name == "fda" for d in docs)
