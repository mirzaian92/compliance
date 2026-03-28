# Operations (v1)

## Daily Run

- Run now (fetch → classify → digest → email):
  - `python -m app.main run-daily`
- Dry run (no email; writes `output/`):
  - `python -m app.main run-daily --dry-run`
- Force resend for the same digest date:
  - `python -m app.main run-daily --force-send`

## Common Failure Cases

- **Missing email env vars** (send will fail fast):
  - `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO`
- **LegiScan disabled**:
  - If `LEGISCAN_API_KEY` is unset, the state collector is skipped (federal sources still run).
- **All sources failed**:
  - `run-daily` exits non-zero and refuses to email a potentially misleading “no updates” digest.
- **OpenAI unavailable**:
  - Classification falls back to deterministic heuristics with `confidence=0.0`.

## Inspecting State

- Sanity check config + DB counters:
  - `python -m app.main health`
- Print the latest saved digest (markdown):
  - `python -m app.main show-latest-digest`

## Safe Resend

- If a digest was already sent for a date, sending is skipped unless forced:
  - `python -m app.main send-digest --force-send`
- Resend uses a stable provider idempotency key per digest date to reduce accidental duplicates.

## Logs

- Logs print to stdout using Python logging.
- Look for the final `run_summary` line for counts and duration.

