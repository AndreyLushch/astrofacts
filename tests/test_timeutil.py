from datetime import date, datetime, timezone

import pytest

from astrofacts.timeutil import UnknownTimezone, day_interval, get_zone


@pytest.mark.parametrize("day, tz, hours", [
    (date(2026, 10, 12), "Europe/Moscow", 24),
    (date(2026, 3, 29), "Europe/Berlin", 23),
    (date(2026, 10, 25), "Europe/Berlin", 25),
    (date(2014, 10, 26), "Europe/Moscow", 25),   # отмена постоянного летнего времени
    (date(2011, 3, 27), "Europe/Moscow", 23),
    (date(1981, 4, 1), "Europe/Moscow", 23),     # первое летнее время в СССР
    (date(2018, 11, 4), "America/Sao_Paulo", 23),  # перевод ровно в полночь: 00:00 не существует
])
def test_day_length(day, tz, hours):
    assert day_interval(day, get_zone(tz)).length_hours == hours


def test_interval_is_local_day():
    interval = day_interval(date(2026, 10, 12), get_zone("Europe/Moscow"))
    assert interval.start == datetime(2026, 10, 11, 21, tzinfo=timezone.utc)
    assert interval.end == datetime(2026, 10, 12, 21, tzinfo=timezone.utc)


def test_missing_midnight_starts_at_transition():
    interval = day_interval(date(2018, 11, 4), get_zone("America/Sao_Paulo"))
    local = interval.start.astimezone(get_zone("America/Sao_Paulo"))
    assert (local.day, local.hour, local.minute) == (4, 1, 0)


def test_unknown_timezone():
    with pytest.raises(UnknownTimezone):
        get_zone("Europe/Nowhere")
