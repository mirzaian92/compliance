from __future__ import annotations

import logging
from datetime import timedelta

from app.config import get_settings
from app.scheduler import Schedule, now_utc, to_local


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

    # We intentionally do NOT use a narrow window here. GitHub Actions scheduled runs can drift,
    # and a tight window can miss the intended send time. Instead:
    # - skip if it's *before* the scheduled local time today (except for a small cross-midnight grace)
    # - run any time *after* the scheduled local time; `run_daily_flow` is idempotent and will skip
    #   quickly once the digest has already been sent for the day.
    local = to_local(dt, schedule.timezone)
    scheduled_today = local.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
    if local < scheduled_today:
        # Grace for schedules near midnight where the runner may start just after midnight.
        scheduled_yesterday = scheduled_today - timedelta(days=1)
        if local - scheduled_yesterday >= timedelta(minutes=60):
            logging.getLogger(__name__).info(
                "Before scheduled time; skipping (now_local=%s tz=%s hour=%s minute=%s)",
                local.isoformat(),
                schedule.timezone,
                schedule.hour,
                schedule.minute,
            )
            return 0

    if local >= scheduled_today:
        logging.getLogger(__name__).info(
            "At/after scheduled time; running (now_local=%s tz=%s hour=%s minute=%s)",
            local.isoformat(),
            schedule.timezone,
            schedule.hour,
            schedule.minute,
        )
    else:
        logging.getLogger(__name__).info(
            "Within cross-midnight grace; running (now_local=%s tz=%s hour=%s minute=%s)",
            local.isoformat(),
            schedule.timezone,
            schedule.hour,
            schedule.minute,
        )

    # Import here so environment checks happen after logging is configured.
    from app.main import run_daily_flow

    return int(run_daily_flow(dry_run=False, force_send=False))


if __name__ == "__main__":
    raise SystemExit(main())
