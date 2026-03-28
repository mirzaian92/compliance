from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import typer

from app.config import get_settings
from app.db import (
    connect,
    get_classification_candidates,
    get_daily_digest,
    get_counts,
    get_latest_daily_digest,
    get_latest_sent_digest,
    has_sent_digest,
    init_db,
    insert_classified_updates,
    insert_normalized_updates,
    insert_raw_documents,
    list_classified_since,
    list_latest,
    upsert_sent_digest,
    upsert_daily_digest,
)
from app.dedupe import candidate_hash
from app.digest import group_for_digest, render_digest, rows_to_entries, write_preview_files
from app.normalize import normalize_row_to_update, pretty_matches_json
from app.sources import fda as fda_source
from app.sources import federal_register as fr_source
from app.sources import legiscan as legiscan_source
from app.classify import classify_row
from app.ai import OpenAIClient
from app.emailer import ResendEmailer
from app.scheduler import digest_date_iso


app = typer.Typer(no_args_is_help=True)
log = logging.getLogger(__name__)


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _normalize_new(conn) -> int:
    from app.db import get_unprocessed_raw_documents

    rows = get_unprocessed_raw_documents(conn)
    updates = [normalize_row_to_update(dict(r)) for r in rows]
    return insert_normalized_updates(conn, updates)


@dataclass(frozen=True)
class SourceRunResult:
    name: str
    ok: bool
    skipped: bool
    fetched: int
    inserted: int
    deduped: int
    error: str | None
    duration_seconds: float


def _fetch_sources(conn) -> list[SourceRunResult]:
    settings = get_settings()
    results: list[SourceRunResult] = []

    def _run(name: str, fetch_fn) -> None:
        started = time.monotonic()
        try:
            docs = fetch_fn()
            inserted, skipped = insert_raw_documents(conn, [(d, candidate_hash(d)) for d in docs])
            results.append(
                SourceRunResult(
                    name=name,
                    ok=True,
                    skipped=False,
                    fetched=len(docs),
                    inserted=inserted,
                    deduped=skipped,
                    error=None,
                    duration_seconds=time.monotonic() - started,
                )
            )
            log.info("source=%s ok fetched=%s inserted=%s deduped=%s", name, len(docs), inserted, skipped)
        except Exception as e:
            msg = str(e)
            is_skipped = name == "LegiScan" and "LEGISCAN_API_KEY" in msg
            results.append(
                SourceRunResult(
                    name=name,
                    ok=False,
                    skipped=is_skipped,
                    fetched=0,
                    inserted=0,
                    deduped=0,
                    error=msg,
                    duration_seconds=time.monotonic() - started,
                )
            )
            if is_skipped:
                log.warning("source=%s skipped reason=%s", name, msg)
            else:
                log.exception("source=%s failed error=%s", name, msg)

    _run("Federal Register", lambda: fr_source.fetch(settings))
    _run("FDA", lambda: fda_source.fetch(settings))
    _run("LegiScan", lambda: legiscan_source.fetch_all_states(settings))
    return results


def _classify_latest(conn, *, since_hours: int, limit: int, no_ai: bool) -> tuple[int, int, int, int, int]:
    settings = get_settings()
    _normalize_new(conn)
    since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    candidates = get_classification_candidates(conn, since_iso=since_dt.isoformat(), limit=limit)

    ai_client = None
    if not no_ai and settings.openai_api_key:
        try:
            ai_client = OpenAIClient(settings)
        except Exception as e:
            logging.getLogger(__name__).warning("AI disabled: %s", e)
            ai_client = None

    records = []
    rejected = 0
    ai_used = 0
    fallback_used = 0
    for r in candidates:
        outcome = classify_row(dict(r), ai_client=ai_client)
        if outcome.rejected or outcome.record is None:
            rejected += 1
            continue
        records.append(outcome.record)
        if outcome.used_ai:
            ai_used += 1
        else:
            fallback_used += 1

    inserted = insert_classified_updates(conn, records)
    return len(candidates), inserted, rejected, ai_used, fallback_used


def _build_digest(conn, *, since_hours: int, digest_date: str | None) -> tuple[str, str, int, str]:
    now = datetime.now(timezone.utc)
    if digest_date is None:
        digest_date = now.date().isoformat()

    since_dt = now - timedelta(hours=since_hours)
    rows = list_classified_since(conn, since_iso=since_dt.isoformat())
    entries = rows_to_entries([dict(r) for r in rows])
    grouped = group_for_digest(entries)
    markdown_body, html_body = render_digest(grouped, digest_date=digest_date, generated_at_iso=now.isoformat())

    upsert_daily_digest(
        conn,
        digest_date_iso=digest_date,
        markdown_body=markdown_body,
        html_body=html_body,
        item_count=grouped.total_items,
        created_at_iso=now.isoformat(),
    )
    return markdown_body, html_body, grouped.total_items, digest_date


@app.command("init-db")
def init_db_cmd() -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    typer.echo(f"Initialized DB at {settings.db_path}")


@app.command("fetch-federal")
def fetch_federal_cmd() -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    docs = fr_source.fetch(settings)
    inserted, skipped = insert_raw_documents(conn, [(d, candidate_hash(d)) for d in docs])
    normalized = _normalize_new(conn)
    typer.echo(
        f"Federal Register: fetched={len(docs)} inserted={inserted} skipped={skipped} normalized={normalized}"
    )


@app.command("fetch-states")
def fetch_states_cmd() -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    docs = legiscan_source.fetch_all_states(settings)
    inserted, skipped = insert_raw_documents(conn, [(d, candidate_hash(d)) for d in docs])
    normalized = _normalize_new(conn)
    typer.echo(f"LegiScan: fetched={len(docs)} inserted={inserted} skipped={skipped} normalized={normalized}")


@app.command("fetch-all")
def fetch_all_cmd() -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    results = _fetch_sources(conn)

    normalized = _normalize_new(conn)
    fetched = sum(r.fetched for r in results)
    inserted = sum(r.inserted for r in results)
    deduped = sum(r.deduped for r in results)
    ok = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if (not r.ok and not r.skipped))
    typer.echo(f"All sources: ok={ok} failed={failed} fetched={fetched} inserted={inserted} deduped={deduped} normalized={normalized}")


@app.command("list-latest")
def list_latest_cmd(limit: int = 20, relevant_only: bool = False) -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    rows = list_latest(conn, limit=limit, relevant_only=relevant_only)
    for r in rows:
        pm = pretty_matches_json(r["product_matches_json"])
        rm = pretty_matches_json(r["reg_matches_json"])
        state_part = f":{r['state_code']}" if r["state_code"] else ""
        typer.echo(
            f"[{r['published_at']}] {r['source_name']} {r['jurisdiction_level']}{state_part} | {r['topic']} | {r['title']}"
        )
        if pm:
            typer.echo(f"  products: {pm}")
        if rm:
            typer.echo(f"  signals:  {rm}")
        typer.echo(f"  url: {r['url']}")


@app.command("health")
def health_cmd() -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    counts = get_counts(conn)
    last_digest = get_latest_daily_digest(conn)
    last_sent = get_latest_sent_digest(conn)
    typer.echo(f"env={settings.app_env} db={settings.db_path} tz={settings.digest_timezone} send_time={settings.digest_hour:02d}:{settings.digest_minute:02d}")
    typer.echo("counts=" + ", ".join([f"{k}={v}" for k, v in counts.items()]))
    if last_digest is not None:
        typer.echo(f"latest_digest_date={last_digest['digest_date']} items={last_digest['item_count']} created_at={last_digest['created_at']}")
    else:
        typer.echo("latest_digest_date=(none)")
    if last_sent is not None:
        typer.echo(f"latest_sent_date={last_sent['digest_date']} message_id={last_sent['message_id']} created_at={last_sent['created_at']}")
    else:
        typer.echo("latest_sent_date=(none)")


@app.command("show-latest-digest")
def show_latest_digest_cmd() -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    row = get_latest_daily_digest(conn)
    if row is None:
        typer.echo("No digests found.")
        raise typer.Exit(code=0)
    typer.echo(str(row["markdown_body"]))


@app.command("classify-latest")
def classify_latest_cmd(
    since_hours: int = 24,
    limit: int = 200,
    no_ai: bool = typer.Option(False, help="Skip OpenAI and use deterministic fallback only."),
) -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    candidates_n, inserted, rejected, ai_used, fallback_used = _classify_latest(
        conn, since_hours=since_hours, limit=limit, no_ai=no_ai
    )
    typer.echo(
        f"classify-latest: candidates={candidates_n} inserted={inserted} rejected={rejected} ai={ai_used} fallback={fallback_used}"
    )


@app.command("build-digest")
def build_digest_cmd(since_hours: int = 24, digest_date: str | None = None) -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    if digest_date is None:
        digest_date = digest_date_iso(datetime.now(timezone.utc), settings.digest_timezone)

    markdown_body, html_body, item_count, digest_date = _build_digest(
        conn, since_hours=since_hours, digest_date=digest_date
    )
    md_path, html_path = write_preview_files(digest_date, markdown_body, html_body)
    typer.echo(f"build-digest: date={digest_date} items={item_count} md={md_path} html={html_path}")


@app.command("preview-digest")
def preview_digest_cmd(since_hours: int = 24, digest_date: str | None = None) -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    if digest_date is None:
        digest_date = digest_date_iso(datetime.now(timezone.utc), settings.digest_timezone)

    markdown_body, html_body, item_count, digest_date = _build_digest(
        conn, since_hours=since_hours, digest_date=digest_date
    )
    md_path, html_path = write_preview_files(digest_date, markdown_body, html_body)
    typer.echo(markdown_body)
    typer.echo(f"preview-digest: date={digest_date} items={item_count} md={md_path} html={html_path}")


@app.command("send-digest")
def send_digest_cmd(
    digest_date: str | None = None,
    dry_run: bool = typer.Option(False, help="Build and print, but do not send email."),
    force_send: bool = typer.Option(False, help="Send even if already sent for this date."),
) -> None:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    now = datetime.now(timezone.utc)
    if digest_date is None:
        digest_date = digest_date_iso(now, settings.digest_timezone)

    if has_sent_digest(conn, digest_date) and not force_send:
        if not dry_run:
            typer.echo(f"send-digest: already sent for {digest_date} (use --force-send to override)")
            raise typer.Exit(code=0)

    row = get_daily_digest(conn, digest_date)
    if row is None:
        markdown_body, html_body, item_count, _ = _build_digest(conn, since_hours=24, digest_date=digest_date)
    else:
        markdown_body = str(row["markdown_body"])
        html_body = str(row["html_body"])
        item_count = int(row["item_count"])

    subject = f"Daily Compliance Update | {digest_date}"
    if dry_run:
        typer.echo(markdown_body)
        typer.echo(f"send-digest (dry-run): date={digest_date} items={item_count}")
        raise typer.Exit(code=0)

    settings.validate_email_required()
    emailer = ResendEmailer(settings)
    idem = None if force_send else f"daily-digest/{digest_date}"
    if force_send:
        idem = f"daily-digest/{digest_date}/force/{now.isoformat()}"
    result = emailer.send_digest(subject=subject, html_body=html_body, text_body=markdown_body, idempotency_key=idem)
    upsert_sent_digest(
        conn,
        digest_date_iso=digest_date,
        subject=subject,
        email_from=settings.email_from or "",
        email_to=settings.email_to or "",
        message_id=result.message_id,
        created_at_iso=now.isoformat(),
    )
    suffix = "already_sent" if result.already_sent else "sent"
    typer.echo(f"send-digest: {suffix} date={digest_date} items={item_count} message_id={result.message_id}")


@app.command("run-daily")
def run_daily_cmd(
    dry_run: bool = typer.Option(False, help="Do everything except sending email."),
    force_send: bool = typer.Option(False, help="Send even if already sent for this date."),
) -> None:
    code = run_daily_flow(dry_run=dry_run, force_send=force_send)
    raise typer.Exit(code=code)


def run_daily_flow(*, dry_run: bool, force_send: bool) -> int:
    _configure_logging()
    settings = get_settings()
    conn = connect(settings.db_path)
    init_db(conn)

    started = time.monotonic()
    now = datetime.now(timezone.utc)
    digest_date = digest_date_iso(now, settings.digest_timezone)

    try:
        if has_sent_digest(conn, digest_date) and not force_send and not dry_run:
            typer.echo(f"run-daily: already sent for {digest_date} (use --force-send to override)")
            return 0

        # Fail fast on missing critical email configuration when we intend to send.
        if not dry_run:
            settings.validate_email_required()

        typer.echo("run-daily: fetching sources...")
        source_results = _fetch_sources(conn)
        sources_attempted = len(source_results)
        sources_ok = sum(1 for r in source_results if r.ok)
        sources_failed = sum(1 for r in source_results if (not r.ok and not r.skipped))
        raw_fetched = sum(r.fetched for r in source_results)
        raw_inserted = sum(r.inserted for r in source_results)
        raw_deduped = sum(r.deduped for r in source_results)
        if sources_ok == 0 and sources_failed > 0:
            raise RuntimeError("All sources failed; refusing to send a potentially misleading digest")
        normalized_inserted = _normalize_new(conn)

        typer.echo("run-daily: classifying latest...")
        candidates_n, inserted, rejected, ai_used, fallback_used = _classify_latest(
            conn, since_hours=24, limit=500, no_ai=False
        )
        typer.echo(
            f"run-daily: classify candidates={candidates_n} inserted={inserted} rejected={rejected} ai={ai_used} fallback={fallback_used}"
        )

        typer.echo("run-daily: building digest...")
        markdown_body, html_body, item_count, digest_date = _build_digest(conn, since_hours=24, digest_date=digest_date)
        md_path, html_path = write_preview_files(digest_date, markdown_body, html_body)

        subject = f"Daily Compliance Update | {digest_date}"
        if dry_run:
            typer.echo(markdown_body)
            typer.echo(f"run-daily (dry-run): date={digest_date} items={item_count} md={md_path} html={html_path}")
            log.info(
                "run_summary date=%s sources_attempted=%s sources_ok=%s sources_failed=%s raw_fetched=%s raw_inserted=%s raw_deduped=%s normalized_inserted=%s classified_inserted=%s digest_items=%s email=%s duration_seconds=%.2f",
                digest_date,
                sources_attempted,
                sources_ok,
                sources_failed,
                raw_fetched,
                raw_inserted,
                raw_deduped,
                normalized_inserted,
                inserted,
                item_count,
                "dry_run",
                time.monotonic() - started,
            )
            return 0

        typer.echo("run-daily: sending email...")
        emailer = ResendEmailer(settings)
        idem = f"daily-digest/{digest_date}" if not force_send else f"daily-digest/{digest_date}/force/{now.isoformat()}"
        result = emailer.send_digest(
            subject=subject,
            html_body=html_body,
            text_body=markdown_body,
            idempotency_key=idem,
        )
        upsert_sent_digest(
            conn,
            digest_date_iso=digest_date,
            subject=subject,
            email_from=settings.email_from or "",
            email_to=settings.email_to or "",
            message_id=result.message_id,
            created_at_iso=now.isoformat(),
        )
        status = "already_sent" if result.already_sent else "sent"
        typer.echo(f"run-daily: success date={digest_date} items={item_count} message_id={result.message_id} status={status}")
        log.info(
            "run_summary date=%s sources_attempted=%s sources_ok=%s sources_failed=%s raw_fetched=%s raw_inserted=%s raw_deduped=%s normalized_inserted=%s classified_inserted=%s digest_items=%s email=%s duration_seconds=%.2f",
            digest_date,
            sources_attempted,
            sources_ok,
            sources_failed,
            raw_fetched,
            raw_inserted,
            raw_deduped,
            normalized_inserted,
            inserted,
            item_count,
            status,
            time.monotonic() - started,
        )
        return 0
    except Exception as e:
        logging.getLogger(__name__).exception("run-daily failed: %s", e)
        log.info("run_summary date=%s email=%s duration_seconds=%.2f", digest_date, "failed", time.monotonic() - started)
        return 1


def main() -> None:
    app()


if __name__ == "__main__":
    main()
