from app.models import PRODUCT_KEYWORDS, REGULATORY_KEYWORDS
from app.normalize import match_keywords


def test_keyword_matching_variants() -> None:
    text = "The agency issued a Warning Letter about DELTA-8 products and 7OH labeling."
    product = match_keywords(text, PRODUCT_KEYWORDS)
    reg = match_keywords(text, REGULATORY_KEYWORDS)
    assert "delta 8" in product or "delta-8" in product
    assert "7OH" in product or "7-OH" in product or "7-hydroxymitragynine" in product
    assert "warning letter" in reg
    assert "labeling" in reg


def test_keyword_matching_multiword_phrase() -> None:
    text = "This proposed rule addresses intoxicating hemp and packaging requirements."
    product = match_keywords(text, PRODUCT_KEYWORDS)
    reg = match_keywords(text, REGULATORY_KEYWORDS)
    assert "intoxicating hemp" in product
    assert "proposed rule" in reg
    assert "packaging" in reg
