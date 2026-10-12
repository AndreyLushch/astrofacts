"""Интервалы Луны без курса по двум конвенциям — материал для ручной сверки с внешним источником.

    python tools/voc_dates.py 2026-10-15 60 [Europe/Moscow]

A — действующая конфигурация (по умолчанию: аспекты к Солнцу — Плутону).
B — только семь классических тел (Солнце — Сатурн).
Строки с пометкой «≠» различают конвенции: начало интервала у них разное.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

from astrofacts.config import Config, load_config
from astrofacts.ephemeris import datetime_from_jd
from astrofacts.sky import scan_day
from astrofacts.types import Body

CLASSIC = (Body.SUN, Body.MERCURY, Body.VENUS, Body.MARS, Body.JUPITER, Body.SATURN)


def intervals(config: Config, first: date, count: int, tz: str) -> dict[float, object]:
    found = {}
    for i in range(count):
        for v in scan_day(first + timedelta(days=i), tz, config, 0).void_of_course:
            found[round(v.end_jd, 5)] = v
    return found


def main() -> None:
    first = date.fromisoformat(sys.argv[1])
    count = int(sys.argv[2])
    tz = sys.argv[3] if len(sys.argv) > 3 else "Europe/Moscow"
    zone = ZoneInfo(tz)
    config = load_config()
    raw = config.model_dump(mode="json")
    raw["void_of_course"]["bodies"] = [b.value for b in CLASSIC]
    a = intervals(config, first, count, tz)
    b = intervals(Config.model_validate(raw), first, count, tz)

    def fmt(jd: float, z=timezone.utc) -> str:
        return (datetime_from_jd(jd) + timedelta(seconds=30)).astimezone(z).strftime("%d.%m %H:%M")

    def last(v) -> str:
        if v.last_aspect is None:
            return "нет аспектов в знаке"
        other = v.last_aspect.body_b if v.last_aspect.body_a is Body.MOON else v.last_aspect.body_a
        return f"{v.last_aspect.aspect.value} {other.value}"

    print(f"Конец интервала (вход Луны в знак) одинаков; времена UTC, в скобках {tz}\n")
    for key in sorted(a):
        va, vb = a[key], b.get(key)
        differs = vb is not None and abs(va.start_jd - vb.start_jd) > 1e-6
        hours = (va.end_jd - va.start_jd) * 24
        line = (f"{'≠' if differs else ' '} конец {fmt(va.end_jd)} ({fmt(va.end_jd, zone)}) -> {va.next_sign.value:<11}"
                f" | A: начало {fmt(va.start_jd)} ({fmt(va.start_jd, zone)}), {hours:5.1f} ч, {last(va)}")
        if differs:
            line += f" | B: начало {fmt(vb.start_jd)} ({fmt(vb.start_jd, zone)}), {last(vb)}"
        print(line)


if __name__ == "__main__":
    main()
