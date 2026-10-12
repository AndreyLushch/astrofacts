"""Сборка ответа и проекция на знаки."""
import json
from datetime import date, datetime, timedelta

import pytest

from astrofacts import ephemeris, schema
from astrofacts.assemble import build_day_facts
from astrofacts.sky import scan_day
from astrofacts.types import SIGN_ORDER, Body, Sign


def facts(config, day, tz="Europe/Moscow", lookahead=0.0) -> schema.DayFacts:
    return build_day_facts(scan_day(day, tz, config, lookahead), config)


@pytest.fixture(scope="module")
def sun_ingress_day(config):
    return facts(config, date(2026, 10, 23), lookahead=6)


def test_roundtrip_through_json(sun_ingress_day):
    raw = sun_ingress_day.model_dump_json()
    assert schema.DayFacts.model_validate_json(raw) == sun_ingress_day


def test_no_absolute_longitudes_in_output(sun_ingress_day):
    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                assert "longitude" not in key and key != "lon", path
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for item in node:
                walk(item, path)
        elif isinstance(node, float):
            # дробные числа в ответе — только длина суток, окно опережения и орб фона
            assert path.endswith(("day_length_hours", "lookahead_hours", "orb_deg")), path

    walk(json.loads(sun_ingress_day.model_dump_json()))


def test_sun_position_agrees_with_ingress(sun_ingress_day):
    sun = sun_ingress_day.background.sun
    assert (sun.at_start.sign, sun.at_start.degree) == (Sign.LIBRA, 29)
    assert (sun.at_end.sign, sun.at_end.degree) == (Sign.SCORPIO, 0)
    (ingress,) = sun_ingress_day.ingresses
    assert (ingress.body, ingress.from_sign, ingress.to_sign) == (Body.SUN, Sign.LIBRA, Sign.SCORPIO)
    assert ingress.when.precision == "minute" and not ingress.retrograde


def test_times_are_local_whole_minutes(sun_ingress_day):
    meta = sun_ingress_day.meta
    assert meta.day_start.isoformat() == "2026-10-23T00:00:00+03:00"
    assert meta.day_end.isoformat() == "2026-10-24T00:00:00+03:00"
    for event in sun_ingress_day.moon.aspects:
        assert event.when.at.second == 0 and event.when.at.utcoffset() == timedelta(hours=3)
        assert event.when.beyond_day == (event.when.at >= meta.day_end)


def test_minutes_are_truncated_not_rounded(config):
    # Начало интервала без курса 03.03.2023 — 14:22:31 UTC
    day = facts(config, date(2023, 3, 3), tz="UTC")
    (voc,) = [v for v in day.moon.void_of_course if not v.starts_before_day]
    assert (voc.start.hour, voc.start.minute) == (14, 22)
    assert (voc.end.hour, voc.end.minute) == (15, 15)
    assert (voc.last_aspect.body, voc.last_aspect.aspect.value) == (Body.PLUTO, "opposition")


def test_moon_and_planet_events_are_not_duplicated(config):
    for offset in range(10):
        day = facts(config, date(2026, 10, 10) + timedelta(days=offset), lookahead=6)
        assert all(Body.MOON in (e.body_a, e.body_b) for e in day.moon.aspects)
        assert all(Body.MOON not in (e.body_a, e.body_b) for e in day.exact_aspects)
        assert all(i.body is not Body.MOON for i in day.ingresses)


def test_solar_houses(sun_ingress_day):
    assert set(sun_ingress_day.signs) == set(Sign)
    positions = {p.body: p for p in sun_ingress_day.bodies}
    for sign, sign_facts in sun_ingress_day.signs.items():
        assert [p.body for p in sign_facts.houses] == list(Body)
        for placement in sign_facts.houses:
            at_start = positions[placement.body].sign_at_start
            expected = (SIGN_ORDER.index(at_start) - SIGN_ORDER.index(sign)) % 12 + 1
            assert placement.house_at_start == expected
    scorpio = sun_ingress_day.signs[Sign.SCORPIO]
    sun = next(p for p in scorpio.houses if p.body is Body.SUN)
    assert (sun.house_at_start, sun.house_at_end) == (12, 1)


def test_rulers(sun_ingress_day, config):
    assert sun_ingress_day.signs[Sign.SCORPIO].ruler.body is Body.PLUTO
    assert sun_ingress_day.signs[Sign.CANCER].ruler.body is Body.MOON
    traditional = config.model_copy(update={"rulers": config.rulers.model_copy(update={"scheme": "traditional"})})
    day = facts(traditional, date(2026, 10, 23))
    assert day.signs[Sign.SCORPIO].ruler.body is Body.MARS
    assert day.signs[Sign.AQUARIUS].ruler.body is Body.SATURN
    assert day.signs[Sign.PISCES].ruler.body is Body.JUPITER


def test_today_is_the_projection_of_day_events(sun_ingress_day):
    day = sun_ingress_day
    aspects = len(day.moon.aspects) + len(day.exact_aspects)
    ingresses = len(day.ingresses) + (1 if day.moon.ingress else 0)
    for sign, sign_facts in day.signs.items():
        kinds = [e.kind for e in sign_facts.today]
        assert kinds.count("exact_aspect") == aspects
        assert kinds.count("house_ingress") == ingresses
        assert kinds.count("lunation") == len(day.lunations)
        # станция из окна на несколько дней вперёд событием суток не является
        assert kinds.count("station") == 0
        ruler = sign_facts.ruler.body
        for event in sign_facts.today:
            if event.kind == "exact_aspect":
                assert event.involves_ruler == (ruler in (event.body_a, event.body_b))
            elif event.kind in ("house_ingress", "station"):
                assert event.involves_ruler == (event.body is ruler)
    scorpio = [e for e in day.signs[Sign.SCORPIO].today if e.kind == "house_ingress" and e.body is Body.SUN]
    assert [(e.from_house, e.to_house) for e in scorpio] == [(12, 1)]


def test_station_day(config):
    day = facts(config, date(2026, 10, 24))
    (station,) = [s for s in day.stations if s.days_ahead == 0]
    assert (station.body, station.direction, station.sign) == (Body.MERCURY, "retrograde", Sign.SCORPIO)
    assert station.when.precision == "minute" and not station.when.beyond_day
    for sign_facts in day.signs.values():
        (event,) = [e for e in sign_facts.today if e.kind == "station"]
        assert event.involves_ruler == (sign_facts.ruler.body is Body.MERCURY)
    week_before = facts(config, date(2026, 10, 17))
    assert [(s.body, s.days_ahead) for s in week_before.stations] == [(Body.MERCURY, 7)]
    assert all(s.when.beyond_day for s in week_before.stations)


def test_slow_pair_aspect_is_dated(config):
    # Сатурн — Нептун, соединение 20.02.2026: взаимная скорость ниже порога
    day = facts(config, date(2026, 2, 20))
    (event,) = [e for e in day.exact_aspects if (e.body_a, e.body_b) == (Body.SATURN, Body.NEPTUNE)]
    assert event.when.precision == "day" and event.when.date == date(2026, 2, 20)
    (slow,) = [a for a in day.background.slow_aspects if (a.body_a, a.body_b) == (Body.SATURN, Body.NEPTUNE)]
    assert slow.state == "exact"
    before = facts(config, date(2026, 2, 10))
    (slow,) = [a for a in before.background.slow_aspects if (a.body_a, a.body_b) == (Body.SATURN, Body.NEPTUNE)]
    assert slow.state == "applying" and 0 < slow.orb_deg <= 3


def test_lunation_and_eclipse(config):
    day = facts(config, date(2026, 8, 12), tz="UTC")
    (lunation,) = day.lunations
    assert (lunation.kind, lunation.sign) == ("new_moon", Sign.LEO)
    assert (lunation.eclipse.kind, lunation.eclipse.type) == ("solar", "total")
    assert day.moon.phase.name == "new_moon"
    assert day.signs[Sign.LEO].today and any(
        e.kind == "lunation" and e.house == 1 and e.eclipse for e in day.signs[Sign.LEO].today
    )
    assert facts(config, date(2026, 8, 15), tz="UTC").moon.phase.name == "waxing_crescent"


def test_phase_names_over_a_month(config):
    names = [facts(config, date(2026, 10, 1) + timedelta(days=i), tz="UTC").moon.phase.name for i in range(31)]
    for principal in ("new_moon", "first_quarter", "full_moon", "last_quarter"):
        assert names.count(principal) == 1, (principal, names)


def test_dst_day(config):
    day = facts(config, date(2026, 10, 25), tz="Europe/Berlin")
    assert day.meta.day_length_hours == 25
    assert day.meta.day_start.utcoffset() == timedelta(hours=2)
    assert day.meta.day_end.utcoffset() == timedelta(hours=1)
