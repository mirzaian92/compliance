from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.models import (
    ClassifiedUpdateRecord,
    NormalizedUpdateRecord,
    RawDocumentCandidate,
)


def connect(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    if p.parent and str(p.parent) not in {".", ""}:
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    # Safer defaults for single-writer scheduled jobs.
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS raw_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            jurisdiction_level TEXT NOT NULL,
            jurisdiction_name TEXT NOT NULL,
            state_code TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_at TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            hash TEXT NOT NULL UNIQUE,
            fetched_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_raw_documents_published_at ON raw_documents(published_at);
        CREATE INDEX IF NOT EXISTS idx_raw_documents_source ON raw_documents(source_name);

        CREATE TABLE IF NOT EXISTS normalized_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_document_id INTEGER NOT NULL UNIQUE,
            topic TEXT NOT NULL,
            product_matches_json TEXT NOT NULL,
            reg_matches_json TEXT NOT NULL,
            summary_stub TEXT NOT NULL,
            is_relevant INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(raw_document_id) REFERENCES raw_documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_normalized_updates_created_at ON normalized_updates(created_at);
        CREATE INDEX IF NOT EXISTS idx_normalized_updates_relevant ON normalized_updates(is_relevant);

        CREATE TABLE IF NOT EXISTS classified_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_document_id INTEGER NOT NULL UNIQUE,
            jurisdiction_level TEXT NOT NULL,
            jurisdiction_name TEXT NOT NULL,
            state_code TEXT,
            category TEXT NOT NULL,
            products_json TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            action_needed INTEGER NOT NULL,
            short_summary TEXT NOT NULL,
            why_it_matters TEXT NOT NULL,
            effective_date TEXT,
            status_label TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(raw_document_id) REFERENCES raw_documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_classified_updates_created_at ON classified_updates(created_at);
        CREATE INDEX IF NOT EXISTS idx_classified_updates_risk ON classified_updates(risk_level);
        CREATE INDEX IF NOT EXISTS idx_classified_updates_jurisdiction ON classified_updates(jurisdiction_level, state_code);

        CREATE TABLE IF NOT EXISTS daily_digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            digest_date TEXT NOT NULL UNIQUE,
            markdown_body TEXT NOT NULL,
            html_body TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_daily_digests_date ON daily_digests(digest_date);

        CREATE TABLE IF NOT EXISTS sent_digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            digest_date TEXT NOT NULL UNIQUE,
            subject TEXT NOT NULL,
            email_from TEXT NOT NULL,
            email_to TEXT NOT NULL,
            message_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sent_digests_date ON sent_digests(digest_date);
        """
    )
    conn.commit()


def insert_raw_documents(
    conn: sqlite3.Connection, items: Iterable[tuple[RawDocumentCandidate, str]]
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for cand, doc_hash in items:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO raw_documents(
                source_name, jurisdiction_level, jurisdiction_name, state_code,
                title, url, published_at, raw_text, hash, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cand.source_name,
                cand.jurisdiction_level.value,
                cand.jurisdiction_name,
                cand.state_code,
                cand.title,
                str(cand.url),
                cand.published_at.isoformat(),
                cand.raw_text,
                doc_hash,
                cand.fetched_at.isoformat(),
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
    conn.commit()
    return inserted, skipped


def get_unprocessed_raw_documents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT r.*
        FROM raw_documents r
        LEFT JOIN normalized_updates n ON n.raw_document_id = r.id
        WHERE n.id IS NULL
        ORDER BY r.published_at DESC, r.id DESC
        """
    )
    return list(cur.fetchall())


def insert_normalized_updates(conn: sqlite3.Connection, updates: Iterable[NormalizedUpdateRecord]) -> int:
    inserted = 0
    for u in updates:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO normalized_updates(
                raw_document_id, topic, product_matches_json, reg_matches_json,
                summary_stub, is_relevant, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                u.raw_document_id,
                u.topic,
                json.dumps(u.product_matches, ensure_ascii=False),
                json.dumps(u.reg_matches, ensure_ascii=False),
                u.summary_stub,
                1 if u.is_relevant else 0,
                u.created_at.isoformat(),
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
    conn.commit()
    return inserted


def insert_classified_updates(conn: sqlite3.Connection, updates: Iterable[ClassifiedUpdateRecord]) -> int:
    inserted = 0
    for u in updates:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO classified_updates(
                raw_document_id, jurisdiction_level, jurisdiction_name, state_code,
                category, products_json, risk_level, action_needed,
                short_summary, why_it_matters, effective_date,
                status_label, confidence, source_url, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                u.raw_document_id,
                u.jurisdiction_level.value,
                u.jurisdiction_name,
                u.state_code,
                u.category.value,
                json.dumps(u.products, ensure_ascii=False),
                u.risk_level.value,
                1 if u.action_needed else 0,
                u.short_summary,
                u.why_it_matters,
                u.effective_date,
                u.status_label.value,
                float(u.confidence),
                str(u.source_url),
                u.created_at.isoformat(),
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
    conn.commit()
    return inserted


def get_classification_candidates(
    conn: sqlite3.Connection, since_iso: str, limit: int = 200
) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT
            r.id AS raw_document_id,
            r.source_name,
            r.jurisdiction_level,
            r.jurisdiction_name,
            r.state_code,
            r.title,
            r.url,
            r.published_at,
            r.raw_text,
            n.product_matches_json,
            n.reg_matches_json,
            n.is_relevant AS keyword_is_relevant
        FROM raw_documents r
        JOIN normalized_updates n ON n.raw_document_id = r.id
        LEFT JOIN classified_updates c ON c.raw_document_id = r.id
        WHERE
            c.id IS NULL
            AND r.published_at >= ?
            AND n.is_relevant = 1
        ORDER BY r.published_at DESC, r.id DESC
        LIMIT ?
        """,
        (since_iso, limit),
    )
    return list(cur.fetchall())


def list_classified_since(conn: sqlite3.Connection, since_iso: str) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT
            c.*,
            r.source_name,
            r.title,
            r.url AS raw_url,
            r.published_at
        FROM classified_updates c
        JOIN raw_documents r ON r.id = c.raw_document_id
        WHERE r.published_at >= ?
        ORDER BY r.published_at DESC, c.id DESC
        """,
        (since_iso,),
    )
    return list(cur.fetchall())


def upsert_daily_digest(
    conn: sqlite3.Connection,
    digest_date_iso: str,
    markdown_body: str,
    html_body: str,
    item_count: int,
    created_at_iso: str,
) -> None:
    conn.execute(
        """
        INSERT INTO daily_digests(digest_date, markdown_body, html_body, item_count, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(digest_date) DO UPDATE SET
            markdown_body=excluded.markdown_body,
            html_body=excluded.html_body,
            item_count=excluded.item_count,
            created_at=excluded.created_at
        """,
        (digest_date_iso, markdown_body, html_body, int(item_count), created_at_iso),
    )
    conn.commit()


def get_daily_digest(conn: sqlite3.Connection, digest_date_iso: str) -> sqlite3.Row | None:
    cur = conn.execute(
        """
        SELECT * FROM daily_digests WHERE digest_date = ? LIMIT 1
        """,
        (digest_date_iso,),
    )
    return cur.fetchone()


def has_sent_digest(conn: sqlite3.Connection, digest_date_iso: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sent_digests WHERE digest_date = ? LIMIT 1",
        (digest_date_iso,),
    )
    return cur.fetchone() is not None


def upsert_sent_digest(
    conn: sqlite3.Connection,
    *,
    digest_date_iso: str,
    subject: str,
    email_from: str,
    email_to: str,
    message_id: str | None,
    created_at_iso: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sent_digests(digest_date, subject, email_from, email_to, message_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(digest_date) DO UPDATE SET
            subject=excluded.subject,
            email_from=excluded.email_from,
            email_to=excluded.email_to,
            message_id=excluded.message_id,
            created_at=excluded.created_at
        """,
        (digest_date_iso, subject, email_from, email_to, message_id, created_at_iso),
    )
    conn.commit()


def list_latest(
    conn: sqlite3.Connection, limit: int = 20, relevant_only: bool = False
) -> list[sqlite3.Row]:
    where = "WHERE n.is_relevant = 1" if relevant_only else ""
    cur = conn.execute(
        f"""
        SELECT
            n.id AS normalized_id,
            n.topic,
            n.product_matches_json,
            n.reg_matches_json,
            n.summary_stub,
            n.is_relevant,
            n.created_at,
            r.source_name,
            r.jurisdiction_level,
            r.jurisdiction_name,
            r.state_code,
            r.title,
            r.url,
            r.published_at
        FROM normalized_updates n
        JOIN raw_documents r ON r.id = n.raw_document_id
        {where}
        ORDER BY r.published_at DESC, n.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(cur.fetchall())


def parse_db_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_latest_daily_digest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT * FROM daily_digests ORDER BY digest_date DESC LIMIT 1",
    )
    return cur.fetchone()


def get_latest_sent_digest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT * FROM sent_digests ORDER BY digest_date DESC LIMIT 1",
    )
    return cur.fetchone()


def get_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ["raw_documents", "normalized_updates", "classified_updates", "daily_digests", "sent_digests"]
    out: dict[str, int] = {}
    for t in tables:
        cur = conn.execute(f"SELECT COUNT(1) AS c FROM {t}")
        out[t] = int(cur.fetchone()["c"])
    return out
