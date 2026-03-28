from datetime import datetime, timezone

from app.dedupe import dedupe_hash


def test_dedupe_is_stable_under_whitespace() -> None:
    published_at = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
    h1 = dedupe_hash("  Test Title ", "https://example.com/a/", published_at, "Hello   world\n")
    h2 = dedupe_hash("Test  Title", "https://example.com/a", published_at, "Hello world")
    assert h1 == h2

