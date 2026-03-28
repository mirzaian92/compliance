from __future__ import annotations

import logging

from app.config import get_settings
from app.scheduler import Schedule, now_utc, should_run_now


def main() -> int:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    schedule = Schedule(
        timezone=settings.digest_timezone,
        hour=int(settings.digest_hour),
        minute=int(settings.digest_minute),
    )
    dt = now_utc()
    if not should_run_now(dt_utc=dt, schedule=schedule, window_minutes=15):
        logging.getLogger(__name__).info(
            "Not within schedule window; skipping (tz=%s hour=%s minute=%s)",
            schedule.timezone,
            schedule.hour,
            schedule.minute,
        )
        return 0

    # Import here so environment checks happen after logging is configured.
    from app.main import run_daily_flow

    return int(run_daily_flow(dry_run=False, force_send=False))


if __name__ == "__main__":
    raise SystemExit(main())

