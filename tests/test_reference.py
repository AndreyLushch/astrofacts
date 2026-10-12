"""Сверка с независимой реализацией: astropy/ERFA по ядру JPL DE432s.

Прецессия, нутация, аберрация и световое время здесь считаются кодом, не связанным
со Swiss Ephemeris. Расхождение означало бы ошибку в выборе системы отсчёта или в логике.
"""
from datetime import date, timedelta

import pytest

from astrofacts import ephemeris
from astrofacts.rootfind import bisect
from astrofacts.sky import scan_day
from astrofacts.types import ASPECT_ANGLE, Body, wrap180

ARCMIN = 1 / 60
# Момент события сверяется с допуском, за который пара проходит угловую минуту, но не меньше минуты.
MINUTE_DAYS = 1 / 1440


@pytest.mark.parametrize("jd", [
    2433300.25,   # 1950
    2440000.5,    # 1968
    2445700.75,   # 1984
    2451545.0,    # 2000
    2456000.125,  # 2012
    2461325.5,    # 2026
    2466000.6,    # 2039
])
@pytest.mark.parametrize("body", list(Body))
def test_positions(reference, body, jd):
    assert abs(wrap180(reference(body, jd) - ephemeris.state(body, jd).longitude)) < ARCMIN


def _tolerance(speed: float) -> float:
    return max(MINUTE_DAYS, ARCMIN / speed)


def test_event_times(reference, config):
    """Моменты ингрессий и точных аспектов, найденные заново по независимым положениям."""
    checked = 0
    for offset in range(0, 28, 3):
        sky = scan_day(date(2026, 10, 1) + timedelta(days=offset), "Europe/Moscow", config)
        for h in sky.ingresses:
            boundary = round(ephemeris.state(h.body, h.jd).longitude / 30) * 30

            def f(jd, body=h.body, boundary=boundary):
                return wrap180(reference(body, jd) - boundary)

            span = 5 * _tolerance(abs(h.speed))
            found = bisect(f, h.jd - span, f(h.jd - span), h.jd + span, f(h.jd + span))
            assert abs(found - h.jd) < _tolerance(abs(h.speed)), h
            checked += 1
        for h in sky.aspects:
            if h.relative_speed < 0.01:
                continue  # у почти неподвижной пары момент точности не определён
            now = wrap180(ephemeris.state(h.body_a, h.jd).longitude - ephemeris.state(h.body_b, h.jd).longitude)
            target = ASPECT_ANGLE[h.aspect] if now >= 0 else -ASPECT_ANGLE[h.aspect]

            def g(jd, h=h, target=target):
                return wrap180(reference(h.body_a, jd) - reference(h.body_b, jd) - target)

            span = 5 * _tolerance(h.relative_speed)
            found = bisect(g, h.jd - span, g(h.jd - span), h.jd + span, g(h.jd + span))
            assert abs(found - h.jd) < _tolerance(h.relative_speed), h
            checked += 1
    assert checked > 30


def test_pluto_station_needs_nutation(reference):
    """Станция Плутона 16.10.2026: независимый расчёт совпадает с нашим только с нутацией.

    Общая сверка положений этого не ловит: ошибка в 17 угловых секунд нутации далеко в пределах
    допуска, а момент станции она сдвигает почти на час.

    Проверяется согласие двух наших реализаций, а не истинность момента: с внешним источником
    станция не сверена (см. комментарий в tests/test_scan.py).
    """
    from datetime import datetime, timezone

    from astropy.coordinates import GeocentricMeanEcliptic, get_body
    from astropy.time import Time

    def mean_longitude(jd):
        moment = Time(jd, format="jd", scale="ut1")
        frame = GeocentricMeanEcliptic(equinox=moment, obstime=moment)
        return float(get_body("pluto", moment).transform_to(frame).lon.deg)

    def station(longitude):
        step = 0.02

        def speed(jd):
            return wrap180(longitude(jd + step) - longitude(jd - step))

        a = ephemeris.jd_from_datetime(datetime(2026, 10, 14, tzinfo=timezone.utc))
        b = ephemeris.jd_from_datetime(datetime(2026, 10, 18, tzinfo=timezone.utc))
        return bisect(speed, a, speed(a), b, speed(b))

    def own_speed(jd):
        return ephemeris.state(Body.PLUTO, jd).speed

    a = ephemeris.jd_from_datetime(datetime(2026, 10, 15, tzinfo=timezone.utc))
    ours = bisect(own_speed, a, own_speed(a), a + 2, own_speed(a + 2))
    with_nutation = station(lambda jd: reference(Body.PLUTO, jd))
    without_nutation = station(mean_longitude)
    assert abs(with_nutation - ours) * 1440 < 3
    assert abs(without_nutation - ours) * 1440 > 30
