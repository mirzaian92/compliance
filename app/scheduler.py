from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Schedule:
    timezone: str
    hour: int
    minute: int


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_local(dt_utc: datetime, tz_name: str) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(tz_name))


def digest_date_iso(dt_utc: datetime, tz_name: str) -> str:
    return to_local(dt_utc, tz_name).date().isoformat()


def scheduled_local_datetime(dt_utc: datetime, schedule: Schedule) -> datetime:
    local = to_local(dt_utc, schedule.timezone)
    return local.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)


def should_run_now(
    *,
    dt_utc: datetime,
    schedule: Schedule,
    window_minutes: int = 15,
) -> bool:
    local = to_local(dt_utc, schedule.timezone)
    scheduled_today = local.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)
    delta_today = local - scheduled_today
    if timedelta(minutes=0) <= delta_today < timedelta(minutes=window_minutes):
        return True

    # Handle the case where the run window crosses midnight (e.g., scheduled 23:55, job runs at 00:00).
    scheduled_yesterday = (scheduled_today - timedelta(days=1))
    delta_yesterday = local - scheduled_yesterday
    return timedelta(minutes=0) <= delta_yesterday < timedelta(minutes=window_minutes)
