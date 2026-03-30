from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.db import get_daily_digest
from app.models import JurisdictionLevel, RiskLevel


@dataclass(frozen=True)
class SnapshotCounts:
    urgent: int
    federal: int
    state: int
    watchlist: int


@dataclass(frozen=True)
class SnapshotUpdate:
    id: int
    raw_document_id: int
    jurisdiction_level: str
    jurisdiction_name: str
    state_code: str | None
    category: str
    products: list[str]
    risk_level: str
    action_needed: bool
    short_summary: str
    why_it_matters: str
    effective_date: str | None
    status_label: str
    confidence: float
    source_url: str
    created_at: str

    section: str
    jurisdiction: str


def _utc_range_for_local_date(digest_date_iso: str, tz_name: str) -> tuple[str, str]:
    d = date.fromisoformat(digest_date_iso)
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time(0, 0), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc.isoformat(), end_utc.isoformat()


def _safe_products(products_json: str | None) -> list[str]:
    if not products_json:
        return []
    try:
        v = json.loads(products_json)
        if isinstance(v, list):
            return [str(x) for x in v if isinstance(x, str)]
    except Exception:
        return []
    return []


def _section_for_update(category: str, risk_level: str, status_label: str, jurisdiction_level: str) -> str:
    if risk_level == RiskLevel.high.value or category in {"warning_letter", "recall", "enforcement_action"}:
        return "Urgent"
    if status_label == "proposed" or category in {"bill_introduced", "proposed_rule"}:
        return "Watchlist"
    if jurisdiction_level == JurisdictionLevel.federal.value:
        return "Federal"
    return "State"


def _counts(updates: list[SnapshotUpdate]) -> SnapshotCounts:
    urgent = sum(1 for u in updates if u.section == "Urgent")
    federal = sum(1 for u in updates if u.section == "Federal")
    state = sum(1 for u in updates if u.section == "State")
    watchlist = sum(1 for u in updates if u.section == "Watchlist")
    return SnapshotCounts(urgent=urgent, federal=federal, state=state, watchlist=watchlist)


def export_dashboard_snapshot(
    conn,
    *,
    digest_date_iso: str,
    tz_name: str,
    out_path: str,
) -> Path:
    start_utc_iso, end_utc_iso = _utc_range_for_local_date(digest_date_iso, tz_name)

    rows = conn.execute(
        """
        SELECT
          id,
          raw_document_id,
          jurisdiction_level,
          jurisdiction_name,
          state_code,
          category,
          products_json,
          risk_level,
          action_needed,
          short_summary,
          why_it_matters,
          effective_date,
          status_label,
          confidence,
          source_url,
          created_at
        FROM classified_updates
        WHERE created_at >= ? AND created_at < ?
        ORDER BY created_at DESC
        """,
        (start_utc_iso, end_utc_iso),
    ).fetchall()

    updates: list[SnapshotUpdate] = []
    for r in rows:
        jurisdiction_level = str(r["jurisdiction_level"])
        jurisdiction_name = str(r["jurisdiction_name"])
        category = str(r["category"])
        risk_level = str(r["risk_level"])
        status_label = str(r["status_label"])
        section = _section_for_update(category, risk_level, status_label, jurisdiction_level)
        jurisdiction = "Federal" if jurisdiction_level == JurisdictionLevel.federal.value else jurisdiction_name

        updates.append(
            SnapshotUpdate(
                id=int(r["id"]),
                raw_document_id=int(r["raw_document_id"]),
                jurisdiction_level=jurisdiction_level,
                jurisdiction_name=jurisdiction_name,
                state_code=str(r["state_code"]) if r["state_code"] else None,
                category=category,
                products=_safe_products(r["products_json"]),
                risk_level=risk_level,
                action_needed=bool(r["action_needed"]),
                short_summary=str(r["short_summary"]),
                why_it_matters=str(r["why_it_matters"]),
                effective_date=str(r["effective_date"]) if r["effective_date"] else None,
                status_label=status_label,
                confidence=float(r["confidence"]),
                source_url=str(r["source_url"]),
                created_at=str(r["created_at"]),
                section=section,
                jurisdiction=jurisdiction,
            )
        )

    # Sort like the digest: urgent first, then federal, state, watchlist; within section: high->low risk then newest.
    section_rank = {"Urgent": 0, "Federal": 1, "State": 2, "Watchlist": 3}
    risk_rank = {"high": 0, "medium": 1, "low": 2}
    updates.sort(
        key=lambda u: (
            section_rank.get(u.section, 99),
            risk_rank.get(u.risk_level, 99),
            u.created_at,
        ),
        reverse=False,
    )

    digest_row = get_daily_digest(conn, digest_date_iso)
    markdown_body = str(digest_row["markdown_body"]) if digest_row else None
    digest_generated_at = str(digest_row["created_at"]) if digest_row else None

    payload = {
        "digest_date": digest_date_iso,
        "generated_at": digest_generated_at,
        "counts": asdict(_counts(updates)),
        "updates": [asdict(u) for u in updates],
        "markdown": markdown_body,
    }

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p

