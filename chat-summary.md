# Compliance Monitor — Chat Summary (Build + Hardening Updates)

This file summarizes the major updates made during the multi-phase build (collect → normalize/dedupe → AI classify → digest → email) and the production-hardening pass.

## What the app does (v1)

- Collects federal + state regulatory/enforcement items related to: hemp/CBD/THC/THCA/delta-8/delta-9, kratom/mitragynine/7-OH, mushroom products (amanita/muscimol/psilocybin), and MGM-15.
- Normalizes + deduplicates raw documents into a common schema.
- Uses an AI layer (OpenAI API) for strict structured classification and short, source-backed summaries, with conservative fallbacks if AI fails.
- Builds one daily digest (Markdown + HTML).
- Sends the digest via Resend as a single daily compliance email.
- Runs on a schedule with explicit timezone handling and duplicate-send protection.

## Phase 1 — Collect + Normalize + Dedupe

- Added SQLite persistence for:
  - `raw_documents`
  - `normalized_updates`
- Implemented collectors:
  - Federal Register (real API integration)
  - FDA (conservative RSS/search parsing aimed at warning letters/recalls/compliance actions)
  - LegiScan (API wrapper; ready for all 50 states; state legislature scrapers can be added later)
- Implemented keyword matching for product + regulatory terms and stored match metadata for downstream summarization.
- Implemented deterministic dedupe based on normalized title/url/published date/text hash.
- Implemented Typer CLI commands (init DB, fetch sources, list latest).

## Phase 2 — AI Classification + Digest Rendering

- Added OpenAI API client using the Responses API with strict structured output (JSON schema) + Pydantic validation.
- Added a deterministic, rule-based relevance gate before AI to reduce false positives and cost.
- Implemented a local fallback classification path when AI fails (items can still be included with raw metadata).
- Added SQLite tables:
  - `classified_updates`
  - `daily_digests`
- Implemented digest grouping:
  - Urgent
  - Federal Updates
  - State Updates
  - Watchlist / Proposed
  - No Significant Updates (when appropriate)
- Added Markdown + HTML templates for the digest.
- Added preview output to `output/` and console printing for dry-runs.

## Phase 3 — Email + Scheduling + Daily Orchestration

- Added Resend email integration:
  - Sends HTML + plaintext
  - Supports comma-separated recipients (`EMAIL_TO`)
  - Deterministic subject: `Daily Compliance Update | YYYY-MM-DD`
  - Retries and readable error handling
- Added DB-level protection against duplicate sends:
  - `sent_digests` table with `digest_date` UNIQUE
  - Resend `Idempotency-Key` per digest date
- Implemented `run-daily` orchestration command:
  1) fetch
  2) normalize
  3) classify
  4) build digest
  5) send email
  6) persist send status
  - returns non-zero on real failures
  - tolerates partial source failures
  - refuses to send a “no updates” digest when *all* sources fail (to avoid misleading emails)
- Added a GitHub Actions workflow for scheduled runs and local scripts for cron/VM usage.

## Production-Hardening Pass (Reliability + Safety)

- Centralized configuration in `app/config.py` with validation and safe defaults.
- Improved SQLite reliability for scheduled jobs (WAL/busy_timeout/synchronous pragmas) and added useful indexes/unique constraints.
- Tightened keyword matching to reduce substring false positives (e.g., avoid short-token accidental matches).
- Improved digest-level dedupe and prioritization (enforcement/recall/warning letters bubble to Urgent).
- Made classification + send idempotent where possible; added robust fallbacks and retries.
- Standardized logging with an end-of-run summary (`run_summary`) including counts and duration.
- Added operational commands:
  - `python -m app.main health`
  - `python -m app.main show-latest-digest`
- Added `OPERATIONS.md` for practical runbook-style usage.

## GitHub Actions improvements (manual test + schedule robustness)

- Added manual workflow modes:
  - `dry-run` (no email)
  - `send`
  - `force-send`
- Made the schedule gating more drift-tolerant so the 7:00 AM send isn’t missed if a scheduled run starts late.

## Key environment variables (high level)

- Sources:
  - `LEGISCAN_API_KEY` (required for LegiScan)
- AI:
  - `OPENAI_API_KEY`, `OPENAI_MODEL`
- Email:
  - `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO`
- Scheduling:
  - `DIGEST_TIMEZONE`, `DIGEST_HOUR`, `DIGEST_MINUTE`
- App:
  - `APP_ENV`, `DB_PATH`, `LOG_LEVEL`

## How to run (typical)

- Dry run (no email): `python -m app.main run-daily --dry-run`
- Send digest: `python -m app.main run-daily`
- Force re-send (same date): `python -m app.main run-daily --force-send`

