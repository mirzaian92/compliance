from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import get_daily_digest
from app.db import list_classified_since
from app.digest import group_for_digest, rows_to_entries
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
    # IMPORTANT: The digest is built from `classified_updates` joined to `raw_documents`,
    # filtered by `raw_documents.published_at >= (generated_at - 24h)`.
    # To ensure the dashboard matches the email digest, we reproduce that selection logic here.
    digest_row = get_daily_digest(conn, digest_date_iso)
    generated_at = None
    since_iso = None
    if digest_row and digest_row["created_at"]:
        generated_at = str(digest_row["created_at"])
        try:
            gen_dt = datetime.fromisoformat(generated_at)
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
        except Exception:
            gen_dt = datetime.now(timezone.utc)
        since_iso = (gen_dt - timedelta(hours=24)).astimezone(timezone.utc).isoformat()
    else:
        # Fallback: if we can't find/parse generated_at, export an empty snapshot.
        generated_at = None
        since_iso = None

    updates: list[SnapshotUpdate] = []
    markdown_body = str(digest_row["markdown_body"]) if digest_row else None

    if since_iso:
        rows = list_classified_since(conn, since_iso=since_iso)
        entries = rows_to_entries([dict(r) for r in rows])
        grouped = group_for_digest(entries)

        def _convert(entry, *, section: str) -> SnapshotUpdate:
            jurisdiction_level = entry.jurisdiction_level.value
            jurisdiction_name = entry.jurisdiction_name
            jurisdiction = "Federal" if entry.jurisdiction_level == JurisdictionLevel.federal else (entry.state_code or entry.jurisdiction_name)
            return SnapshotUpdate(
                # Use raw_document_id as a stable identifier for UI rendering.
                id=int(entry.raw_document_id),
                raw_document_id=int(entry.raw_document_id),
                jurisdiction_level=jurisdiction_level,
                jurisdiction_name=jurisdiction_name,
                state_code=entry.state_code,
                category=entry.category.value,
                products=list(entry.products),
                risk_level=entry.risk_level.value,
                action_needed=bool(entry.action_needed),
                short_summary=entry.short_summary,
                why_it_matters=entry.why_it_matters,
                effective_date=entry.effective_date,
                status_label=entry.status_label.value,
                confidence=float(entry.confidence),
                source_url=entry.source_url,
                created_at=entry.published_at,
                section=section,
                jurisdiction=jurisdiction,
            )

        for e in grouped.urgent:
            updates.append(_convert(e, section="Urgent"))
        for e in grouped.federal:
            updates.append(_convert(e, section="Federal"))
        for e in grouped.state:
            updates.append(_convert(e, section="State"))
        for e in grouped.watchlist:
            updates.append(_convert(e, section="Watchlist"))

    payload = {
        "digest_date": digest_date_iso,
        "generated_at": generated_at,
        "counts": asdict(_counts(updates)) if updates else {"urgent": 0, "federal": 0, "state": 0, "watchlist": 0},
        "updates": [asdict(u) for u in updates],
        "markdown": markdown_body,
    }

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
