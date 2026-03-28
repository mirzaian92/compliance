from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JurisdictionLevel(StrEnum):
    federal = "federal"
    state = "state"


class UpdateCategory(StrEnum):
    bill_introduced = "bill_introduced"
    bill_passed = "bill_passed"
    final_rule = "final_rule"
    proposed_rule = "proposed_rule"
    warning_letter = "warning_letter"
    recall = "recall"
    enforcement_action = "enforcement_action"
    agency_notice = "agency_notice"
    other_regulatory_update = "other_regulatory_update"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class StatusLabel(StrEnum):
    proposed = "proposed"
    enacted = "enacted"
    effective = "effective"
    enforcement = "enforcement"
    recall = "recall"
    notice = "notice"
    unknown = "unknown"


class AIClassificationResult(BaseModel):
    is_relevant: bool
    jurisdiction_level: JurisdictionLevel
    jurisdiction_name: str
    state_code: str | None = None
    category: UpdateCategory
    products: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    action_needed: bool
    short_summary: str
    why_it_matters: str
    effective_date: str | None = None
    status_label: StatusLabel
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("jurisdiction_name", "state_code", "short_summary", "why_it_matters", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _validate_state(self) -> "AIClassificationResult":
        if self.jurisdiction_level == JurisdictionLevel.state and not self.state_code:
            raise ValueError("state_code is required when jurisdiction_level=state")
        return self


class ClassifiedUpdateRecord(BaseModel):
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
    source_url: HttpUrl
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_created_at(cls, v: Any) -> datetime:
        return coerce_datetime(v)


def coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str):
        v = value.strip()
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
    raise ValueError(f"Unsupported datetime value: {value!r}")


class RawDocumentCandidate(BaseModel):
    source_name: str
    jurisdiction_level: JurisdictionLevel
    jurisdiction_name: str
    state_code: str | None = None

    title: str
    url: HttpUrl
    published_at: datetime
    raw_text: str
    fetched_at: datetime = Field(default_factory=utc_now)

    @field_validator("source_name", "jurisdiction_name", "state_code", "title", "raw_text", mode="before")
    @classmethod
    def _strip_strings(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("published_at", "fetched_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> datetime:
        return coerce_datetime(v)

    @model_validator(mode="after")
    def _nonempty(self) -> "RawDocumentCandidate":
        if not self.title:
            raise ValueError("title must be non-empty")
        if not self.raw_text:
            raise ValueError("raw_text must be non-empty")
        if self.jurisdiction_level == JurisdictionLevel.state and not self.state_code:
            raise ValueError("state_code is required for state jurisdiction")
        return self


class NormalizedUpdateRecord(BaseModel):
    raw_document_id: int
    topic: str
    product_matches: list[str]
    reg_matches: list[str]
    summary_stub: str
    is_relevant: bool
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_created(cls, v: Any) -> datetime:
        return coerce_datetime(v)


PRODUCT_KEYWORDS: list[str] = [
    "hemp",
    "cannabidiol",
    "CBD",
    "THC",
    "THCA",
    "delta-8",
    "delta 8",
    "delta-9",
    "delta 9",
    "intoxicating hemp",
    "kratom",
    "mitragynine",
    "7-hydroxymitragynine",
    "7-OH",
    "7OH",
    "mushroom",
    "amanita",
    "amanita muscaria",
    "muscimol",
    "ibotenic acid",
    "psilocybin",
    "psilocin",
    "MGM-15",
    "MGM15",
]

REGULATORY_KEYWORDS: list[str] = [
    "bill",
    "law",
    "regulation",
    "rule",
    "notice",
    "final rule",
    "proposed rule",
    "warning letter",
    "recall",
    "enforcement",
    "restriction",
    "prohibited",
    "ban",
    "compliance",
    "legal status",
    "labeling",
    "packaging",
    "testing",
    "sale",
    "distribution",
]


@dataclass(frozen=True)
class IngestStats:
    fetched: int
    inserted: int
    skipped_duplicates: int
