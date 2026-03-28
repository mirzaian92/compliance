from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import JurisdictionLevel, RiskLevel, StatusLabel, UpdateCategory
from app.dedupe import normalize_url
from app.normalize import normalize_for_matching


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DigestEntry:
    raw_document_id: int
    jurisdiction_level: JurisdictionLevel
    jurisdiction_name: str
    state_code: str | None
    category: UpdateCategory
    products: list[str]
    risk_level: RiskLevel
    action_needed: bool
    short_summary: str
    why_it_matters: str
    effective_date: str | None
    status_label: StatusLabel
    confidence: float
    source_url: str
    published_at: str
    source_name: str
    title: str

    @property
    def jurisdiction_label(self) -> str:
        if self.jurisdiction_level == JurisdictionLevel.state:
            return self.state_code or self.jurisdiction_name
        return "Federal"

    @property
    def products_label(self) -> str:
        if not self.products:
            return "unknown"
        return ", ".join(self.products[:6])


def _loads_list(text: str) -> list[str]:
    try:
        v = json.loads(text)
    except Exception:
        return []
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def rows_to_entries(rows: list[dict[str, Any]]) -> list[DigestEntry]:
    out: list[DigestEntry] = []
    for r in rows:
        out.append(
            DigestEntry(
                raw_document_id=int(r["raw_document_id"]),
                jurisdiction_level=JurisdictionLevel(str(r["jurisdiction_level"])),
                jurisdiction_name=str(r["jurisdiction_name"]),
                state_code=str(r["state_code"]) if r.get("state_code") else None,
                category=UpdateCategory(str(r["category"])),
                products=_loads_list(r["products_json"]),
                risk_level=RiskLevel(str(r["risk_level"])),
                action_needed=bool(int(r["action_needed"])),
                short_summary=str(r["short_summary"]),
                why_it_matters=str(r["why_it_matters"]),
                effective_date=str(r["effective_date"]) if r.get("effective_date") else None,
                status_label=StatusLabel(str(r["status_label"])),
                confidence=float(r["confidence"]),
                source_url=str(r["source_url"]),
                published_at=str(r["published_at"]),
                source_name=str(r["source_name"]),
                title=str(r["title"]),
            )
        )
    return out


def _is_watchlist(e: DigestEntry) -> bool:
    if e.status_label == StatusLabel.proposed:
        return True
    if e.category in {UpdateCategory.bill_introduced, UpdateCategory.proposed_rule}:
        return True
    return False


def _is_urgent(e: DigestEntry) -> bool:
    if e.risk_level == RiskLevel.high:
        return True
    if e.category in {UpdateCategory.recall, UpdateCategory.warning_letter, UpdateCategory.enforcement_action}:
        return True
    if e.action_needed:
        return True
    return False


def _digest_dedupe(entries: list[DigestEntry]) -> list[DigestEntry]:
    # Simple, deterministic: keep highest-confidence per (jurisdiction, normalized URL or title)
    best: dict[tuple[str, str], DigestEntry] = {}
    for e in entries:
        key_value = normalize_url(e.source_url) if e.source_url else normalize_for_matching(e.title)
        key = (e.jurisdiction_label, key_value)
        cur = best.get(key)
        if cur is None or e.confidence > cur.confidence:
            best[key] = e
    return list(best.values())


@dataclass(frozen=True)
class GroupedDigest:
    urgent: list[DigestEntry]
    federal: list[DigestEntry]
    state: list[DigestEntry]
    watchlist: list[DigestEntry]

    @property
    def total_items(self) -> int:
        return len(self.urgent) + len(self.federal) + len(self.state) + len(self.watchlist)


def group_for_digest(entries: list[DigestEntry]) -> GroupedDigest:
    entries = _digest_dedupe(entries)
    entries.sort(key=lambda e: (e.published_at, e.jurisdiction_label, e.risk_level.value), reverse=True)

    urgent: list[DigestEntry] = []
    federal: list[DigestEntry] = []
    state: list[DigestEntry] = []
    watchlist: list[DigestEntry] = []

    for e in entries:
        if _is_urgent(e):
            urgent.append(e)
        elif _is_watchlist(e):
            watchlist.append(e)
        elif e.jurisdiction_level == JurisdictionLevel.federal:
            federal.append(e)
        else:
            state.append(e)

    return GroupedDigest(urgent=urgent, federal=federal, state=state, watchlist=watchlist)


def _env() -> Environment:
    template_dir = Path(__file__).parent / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_digest(grouped: GroupedDigest, *, digest_date: str, generated_at_iso: str) -> tuple[str, str]:
    env = _env()
    md_tpl = env.get_template("digest.md.j2")
    html_tpl = env.get_template("digest.html.j2")
    ctx = {
        "digest_date": digest_date,
        "generated_at": generated_at_iso,
        "urgent": grouped.urgent,
        "federal": grouped.federal,
        "state": grouped.state,
        "watchlist": grouped.watchlist,
        "total_items": grouped.total_items,
    }
    return md_tpl.render(**ctx), html_tpl.render(**ctx)


def write_preview_files(digest_date: str, markdown_body: str, html_body: str) -> tuple[Path, Path]:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"digest_{digest_date}.md"
    html_path = out_dir / f"digest_{digest_date}.html"
    md_path.write_text(markdown_body, encoding="utf-8")
    html_path.write_text(html_body, encoding="utf-8")
    return md_path, html_path
