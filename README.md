# Compliance Monitoring (Phase 1)

Phase 1 builds the **collector + normalization pipeline** for daily regulatory updates across:

- Federal Register (federal)
- FDA pages/feeds likely to surface warning letters / recalls / enforcement
- LegiScan (state bills / legislative activity)

Focus products:
hemp / cannabinoids (CBD, THC, THCA, delta-8/9), kratom (mitragynine, 7-OH), mushroom products (amanita/muscimol, psilocybin/psilocin), MGM-15.

## Setup

1. Create a virtualenv (Python 3.11).
2. Install deps:
   - `pip install -r requirements.txt`
3. Create `.env` from `.env.example`:
   - `Copy-Item .env.example .env` (PowerShell)
4. Add `LEGISCAN_API_KEY` to `.env` to enable state fetching.
5. (Optional) Add `OPENAI_API_KEY` + set `OPENAI_MODEL` to enable AI classification.
6. (Email) Add `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO` to enable daily digest emails.

Optional environments:
- Set `APP_ENV=prod` and create `.env.prod` for production overrides.

## Commands

All commands run as `python -m app.main ...`

- `init-db`  
  Creates the SQLite schema (raw + normalized tables).

- `fetch-federal`  
  Fetches recent Federal Register documents and stores raw + normalized records.

- `fetch-states`  
  Fetches recent LegiScan results across all 50 states (requires `LEGISCAN_API_KEY`).

- `fetch-all`  
  Runs Federal Register + FDA + LegiScan collectors.

- `list-latest`  
  Prints the most recent normalized updates from the DB.

- `classify-latest`  
  Runs AI (or deterministic fallback) to filter + classify recent items into `classified_updates`.

- `build-digest`  
  Builds the daily digest from classified items (last 24 hours by default), saves `output/digest_YYYY-MM-DD.md` and `.html`, and stores it in `daily_digests`.

- `preview-digest`  
  Same as `build-digest` but also prints the markdown digest to the console.

- `send-digest`  
  Sends the saved digest email for a date (builds it if missing). Duplicate-protected unless `--force-send`.

- `run-daily`  
  End-to-end daily job: fetch → classify → build digest → email. Supports `--dry-run` and `--force-send`.

## What’s Stored

- `raw_documents` holds the fetched document metadata + a text snippet for downstream AI summarization.
- `normalized_updates` stores keyword matches, topic, and a stub summary placeholder.
- `classified_updates` stores the AI-validated relevance + concise summaries + risk labels for digesting.
- `daily_digests` stores the rendered markdown + HTML digest bodies.
- `sent_digests` stores one “sent” record per digest date (duplicate-send protection).

## SQLite Notes (v1)

SQLite is acceptable for v1 if you run **one scheduled job at a time** (single writer). For GitHub Actions, you must
persist the DB between runs (the workflow caches `data/`). For higher volume or multiple concurrent workers, migrate to Postgres.

## Current Limitations

- FDA collection is conservative and heuristic (feeds/search HTML can change).
- LegiScan collection depends on API availability and your subscription limits.
- If OpenAI is unavailable, classification falls back to deterministic heuristics with `confidence=0.0`.
- No state legislature site scrapers yet (code is structured to add them later).

## Email (Resend)

1. Create a Resend account and API key.
2. Verify your sending domain/address in Resend.
3. Set these env vars in `.env` (or your production secret store):
   - `RESEND_API_KEY`
   - `EMAIL_FROM` (must be a verified sender)
   - `EMAIL_TO` (comma-separated recipients)

Subject format: `Daily Compliance Update | YYYY-MM-DD`
Idempotency: the sender uses a stable `Idempotency-Key` per digest date to reduce accidental duplicate sends.

## Run Once (Manual)

- Fetch + classify + build + send:
  - `python -m app.main run-daily`
- Dry run (no email send; still writes `output/` files):
  - `python -m app.main run-daily --dry-run`
- Force resend for the same date:
  - `python -m app.main run-daily --force-send`

## Scheduling

### GitHub Actions

The workflow `.github/workflows/daily.yml` runs every 15 minutes and only executes the job during a 15-minute
window defined by:

- `DIGEST_TIMEZONE`
- `DIGEST_HOUR`
- `DIGEST_MINUTE`

Configure GitHub **Secrets**:

- `OPENAI_API_KEY`
- `LEGISCAN_API_KEY`
- `RESEND_API_KEY`

Configure GitHub **Variables**:

- `OPENAI_MODEL`
- `EMAIL_FROM`
- `EMAIL_TO`
- `DIGEST_TIMEZONE`
- `DIGEST_HOUR`
- `DIGEST_MINUTE`

Important: GitHub Actions cron schedules run in UTC. This repo runs every 15 minutes and the app enforces the local-time window using `DIGEST_TIMEZONE`.

Persistence: GitHub Actions runners are ephemeral; the workflow caches `data/` so `data/compliance.db` survives between runs (required for duplicate-send protection).

### Cron on a VM/Server

Run this every 15 minutes:

- `scripts/run_daily.sh`

It will only run the pipeline during the schedule window and is protected against duplicate sends per date.

## Dashboard (Next.js)

This repo also includes a simple internal dashboard UI under `dashboard/` (Next.js App Router + TypeScript).
It does **not** replace the Python pipeline or the daily email workflow. The dashboard is read-only and
consumes a daily JSON snapshot exported by the pipeline at `dashboard/public/data/latest.json` (committed by GitHub Actions).

### Run the dashboard locally

1. Install Node dependencies:
   - `cd dashboard`
   - `npm install`
3. Start:
   - `npm run dev`
4. Open:
   - `http://localhost:3000`

### Deploy to Vercel (simple)

1. Import the GitHub repo into Vercel.
2. Set **Root Directory** to `dashboard/`.
3. Deploy.

Optional (UI timezone label):
- Set Vercel env var `NEXT_PUBLIC_DIGEST_TIMEZONE` (default: `America/Los_Angeles`).

Data flow:
- GitHub Actions runs the Python pipeline daily (email still sends).
- After the pipeline builds the digest, it runs `python -m app.main export-dashboard` and commits `dashboard/public/data/latest.json`.
- Vercel redeploys on every push to `main`, so the dashboard updates once per day after the scheduled run.

If you prefer not to commit digest content to git history, move the snapshot to object storage later (S3/R2) and have the dashboard fetch it.

### What it shows (v1)

- Homepage: today’s digest date, section counts, and today’s update cards.
- Left sidebar: all 50 states (placeholder routes).
- State pages: `/states/[stateCode]` placeholders (no state-specific logic yet).
