"""Локальные сутки как интервал абсолютного времени."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnknownTimezone(ValueError):
    pass


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise UnknownTimezone(f"неизвестная таймзона: {name!r}") from e


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """Первый момент календарной даты в зоне, в UTC.

    Если полночи в этот день нет (часы переведены вперёд ровно в 00:00), zoneinfo толкует её
    по смещению до перевода, и получается момент перевода — он и есть начало суток.
    """
    return datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class DayInterval:
    """Полуоткрытый интервал [start, end) в UTC."""
    day: date
    zone: ZoneInfo
    start: datetime
    end: datetime

    @property
    def length_hours(self) -> float:
        return (self.end - self.start) / timedelta(hours=1)


def day_interval(day: date, zone: ZoneInfo) -> DayInterval:
    return DayInterval(day, zone, local_midnight(day, zone), local_midnight(day + timedelta(days=1), zone))
