"""Значения, сверенные вручную с внешним источником (tests/manual/astroseek.toml)."""
import tomllib
from datetime import date
from pathlib import Path

import pytest

from astrofacts.assemble import build_day_facts
from astrofacts.sky import scan_day

REFERENCE = tomllib.loads((Path(__file__).parent / "manual" / "astroseek.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("point", REFERENCE["void_of_course"], ids=lambda p: p["date"])
def test_void_of_course_start(config, point):
    day = date.fromisoformat(point["date"])
    facts = build_day_facts(scan_day(day, point["tz"], config), config)
    starts = [v.start.strftime("%H:%M") for v in facts.moon.void_of_course if v.start.date() == day]
    assert starts == [point["start"]]


@pytest.mark.parametrize("point", REFERENCE["station"], ids=lambda p: f"{p['body']}-{p['date']}")
def test_station(config, point):
    day = date.fromisoformat(point["date"])
    facts = build_day_facts(scan_day(day, point["tz"], config), config)
    found = [
        (s.body.value, s.direction, s.when.at.strftime("%H:%M")) for s in facts.stations if s.days_ahead == 0
    ]
    assert found == [(point["body"], point["direction"], point["time"])]
