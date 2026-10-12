"""Сканирование суток: внутренняя согласованность и известные астрономические события."""
from datetime import date, datetime, timedelta, timezone

import pytest

from astrofacts import ephemeris
from astrofacts.sky import scan_day
from astrofacts.types import ASPECT_ANGLE, Aspect, Body, Sign, wrap180

ARCSEC = 1 / 3600
MINUTE = timedelta(minutes=1)


def utc(jd: float) -> datetime:
    return ephemeris.datetime_from_jd(jd)


def days(first: date, count: int):
    return [first + timedelta(days=i) for i in range(count)]


@pytest.fixture(scope="module")
def month(config):
    return [scan_day(d, "Europe/Moscow", config, 6) for d in days(date(2026, 10, 1), 31)]


def test_aspects_are_exact(month):
    seen = 0
    for sky in month:
        for h in sky.aspects:
            a = ephemeris.state(h.body_a, h.jd).longitude
            b = ephemeris.state(h.body_b, h.jd).longitude
            off = abs(abs(wrap180(a - b)) - ASPECT_ANGLE[h.aspect])
            # у почти неподвижной пары момент определён хуже, чем угол
            assert off < ARCSEC, (h, off)
            assert sky.start_jd <= h.jd < sky.lookahead_end_jd
            seen += 1
    assert seen > 100


def test_ingresses_and_stations_are_exact(month):
    ingresses = stations = 0
    for sky in month:
        for h in sky.ingresses:
            lon = ephemeris.state(h.body, h.jd).longitude
            assert abs(wrap180(lon - round(lon / 30) * 30)) < ARCSEC
            assert ephemeris.state(h.body, h.jd + 0.01).longitude // 30 != ephemeris.state(h.body, h.jd - 0.01).longitude // 30
            ingresses += 1
        for h in sky.stations:
            assert abs(ephemeris.state(h.body, h.jd).speed) < 1e-4
            before, after = ephemeris.state(h.body, h.jd - 1).speed, ephemeris.state(h.body, h.jd + 1).speed
            assert (before > 0 > after) if h.direction == "retrograde" else (before < 0 < after)
            stations += 1
    assert ingresses > 12 and stations > 0


def test_events_tile_the_month_without_gaps_or_repeats(config):
    """Сутки — полуоткрытые интервалы: событие на границе принадлежит ровно одним суткам."""
    skies = [scan_day(d, "Europe/Moscow", config) for d in days(date(2026, 10, 1), 31)]
    per_day = [(h.body_a, h.body_b, h.aspect, round(h.jd, 6)) for sky in skies for h in sky.aspects]
    assert len(per_day) == len(set(per_day))
    for earlier, later in zip(skies, skies[1:]):
        assert earlier.end_jd == later.start_jd


def test_lookahead_marks_events_beyond_day(config):
    plain = scan_day(date(2026, 10, 12), "Europe/Moscow", config, 0)
    ahead = scan_day(date(2026, 10, 12), "Europe/Moscow", config, 6)
    assert ahead.lookahead_end_jd - ahead.end_jd == pytest.approx(0.25)
    assert [h for h in ahead.aspects if not ahead.beyond_day(h.jd)] == list(plain.aspects)
    assert all(not plain.beyond_day(h.jd) for h in plain.aspects)
    with pytest.raises(ValueError):
        scan_day(date(2026, 10, 12), "Europe/Moscow", config, 100)


def test_void_of_course_ends_at_ingress_and_has_no_aspects_inside(month, config):
    seen = 0
    voc = config.void_of_course
    for sky in month:
        for v in sky.void_of_course:
            assert v.start_jd < v.end_jd
            moon = ephemeris.state(Body.MOON, v.end_jd).longitude
            assert abs(wrap180(moon - round(moon / 30) * 30)) < ARCSEC
            assert v.next_sign is not v.sign
            # прямой перебор по минутам: внутри интервала ни одного точного аспекта
            jd = v.start_jd + 2 / 1440
            while jd < v.end_jd - 2 / 1440:
                m = ephemeris.state(Body.MOON, jd).longitude
                for body in voc.bodies:
                    sep = abs(wrap180(m - ephemeris.state(body, jd).longitude))
                    for aspect in voc.aspects:
                        assert abs(sep - ASPECT_ANGLE[aspect]) > 0.5 / 60, (v, body, aspect)
                jd += 1 / 1440
            seen += 1
    assert seen > 10


def test_trajectory_matches_ephemeris(month):
    sky = month[11]
    for body, tr in sky.trajectories.items():
        for jd in (sky.start_jd + 0.0123, sky.start_jd + 0.5371, sky.end_jd - 0.0007):
            exact = ephemeris.state(body, jd)
            assert abs(wrap180(tr.at(jd).longitude - exact.longitude)) < 0.1 * ARCSEC
            assert abs(tr.at(jd).speed - exact.speed) < 1e-3


def test_dst_days_have_23_and_25_hours(config):
    assert scan_day(date(2026, 3, 29), "Europe/Berlin", config).length_hours == 23
    assert scan_day(date(2026, 10, 25), "Europe/Berlin", config).length_hours == 25


# --- события, известные из астрономических публикаций (время UTC) ---

def test_total_solar_eclipse_2026_08_12(config):
    sky = scan_day(date(2026, 8, 12), "UTC", config)
    (lunation,) = sky.lunations
    assert lunation.kind == "new_moon"
    assert abs(utc(lunation.jd) - datetime(2026, 8, 12, 17, 37, tzinfo=timezone.utc)) < MINUTE
    assert (lunation.eclipse.kind, lunation.eclipse.type) == ("solar", "total")
    assert abs(utc(lunation.eclipse.max_jd) - datetime(2026, 8, 12, 17, 46, tzinfo=timezone.utc)) < MINUTE


def test_total_lunar_eclipse_2026_03_03(config):
    sky = scan_day(date(2026, 3, 3), "UTC", config)
    (lunation,) = sky.lunations
    assert lunation.kind == "full_moon"
    assert (lunation.eclipse.kind, lunation.eclipse.type) == ("lunar", "total")
    assert abs(utc(lunation.eclipse.max_jd) - datetime(2026, 3, 3, 11, 34, tzinfo=timezone.utc)) < MINUTE


def test_ordinary_lunation_has_no_eclipse(config):
    sky = scan_day(date(2026, 10, 10), "UTC", config)
    (lunation,) = sky.lunations
    assert lunation.kind == "new_moon" and lunation.eclipse is None


def test_march_equinox_2026(config):
    sky = scan_day(date(2026, 3, 20), "UTC", config)
    (sun,) = [h for h in sky.ingresses if h.body is Body.SUN]
    assert (sun.from_sign, sun.to_sign) == (Sign.PISCES, Sign.ARIES)
    assert abs(utc(sun.jd) - datetime(2026, 3, 20, 14, 46, tzinfo=timezone.utc)) < MINUTE


def test_slow_events_are_not_timed(month, config):
    for sky in month:
        for h in sky.aspects:
            assert h.timed == (h.relative_speed >= config.speed.slow_threshold_deg_per_day)
        for h in sky.slow_aspects:
            assert config.is_slow(h.body_a) and config.is_slow(h.body_b)
            assert h.exact_today or min(h.orb_start, h.orb_end) <= config.orbs.background[h.aspect]
