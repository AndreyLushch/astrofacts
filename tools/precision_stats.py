"""Сколько аспектов получает пометку slow_pair при текущем пороге скорости.

    python tools/precision_stats.py 2026-02-01 60 [Europe/Moscow]
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from astrofacts.config import load_config
from astrofacts.ephemeris import datetime_from_jd
from astrofacts.sky import scan_day
from astrofacts.types import Body


def main() -> None:
    first = date.fromisoformat(sys.argv[1])
    count = int(sys.argv[2])
    tz = sys.argv[3] if len(sys.argv) > 3 else "Europe/Moscow"
    zone = ZoneInfo(tz)
    config = load_config()
    threshold = config.speed.slow_threshold_deg_per_day

    def local(jd: float) -> str:
        return datetime_from_jd(jd).astimezone(zone).strftime("%Y-%m-%d %H:%M")

    totals: Counter[str] = Counter()
    dated: list[str] = []
    for i in range(count):
        sky = scan_day(first + timedelta(days=i), tz, config, 0)
        for h in sky.aspects:
            group = "аспекты Луны" if h.body_a is Body.MOON or h.body_b is Body.MOON else "аспекты планет"
            totals[f"{group}: {'slow_pair' if h.slow_pair else 'обычные'}"] += 1
            if h.slow_pair:
                dated.append(f"{local(h.jd)}  {h.body_a.value} {h.aspect.value} {h.body_b.value}"
                             f"  взаимная скорость {h.relative_speed:.3f}°/сут")
        for h in sky.ingresses:
            totals["ингрессии"] += 1
        for h in sky.stations:
            if sky.start_jd <= h.jd < sky.end_jd:
                totals["станции"] += 1
                print(f"станция {local(h.jd)}  {h.body.value} {h.direction}")

    print(f"\n{first} + {count} сут., {tz}, порог {threshold}°/сут")
    for key in sorted(totals):
        print(f"  {key}: {totals[key]}")
    print("\nАспекты с пометкой slow_pair:")
    for line in dated:
        print("  " + line)


if __name__ == "__main__":
    main()
