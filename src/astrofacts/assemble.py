"""Сборка ответа: DaySky -> DayFacts.

Здесь точные долготы и юлианские даты превращаются в знаки, дома и локальное время.
"""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from . import __version__, schema
from .config import Config
from .ephemeris import datetime_from_jd
from .frames import Frame, SolarSignFrame
from .sky.model import AspectHit, DaySky
from .types import SIGN_ORDER, Aspect, Body, Sign, sign_of
from .zodiac import ruler_of

_QUARTERS = ("new_moon", "first_quarter", "full_moon", "last_quarter")
_BETWEEN = ("waxing_crescent", "waxing_gibbous", "waning_gibbous", "waning_crescent")


@lru_cache(maxsize=1)
def tzdata_version() -> str:
    for directory in zoneinfo.TZPATH:
        try:
            with (Path(directory) / "tzdata.zi").open(encoding="utf-8") as f:
                first = f.readline()
        except OSError:
            continue
        if first.startswith("# version"):
            return first.split()[-1]
    try:
        return metadata.version("tzdata")
    except metadata.PackageNotFoundError:
        return "unknown"


class _Clock:
    """Перевод моментов DaySky в локальное время запроса."""

    def __init__(self, sky: DaySky) -> None:
        self.sky = sky
        self.zone = zoneinfo.ZoneInfo(sky.tz)

    def local(self, jd: float) -> datetime:
        # Минута усекается, а не округляется: так принято в астрологических календарях,
        # и момент не «уезжает» в следующую минуту, час или сутки.
        moment = datetime_from_jd(jd) + timedelta(microseconds=500)  # погрешность представления JD
        return moment.replace(second=0, microsecond=0).astimezone(self.zone)

    def when(self, jd: float, timed: bool = True) -> schema.TimedWhen | schema.DatedWhen:
        beyond = self.sky.beyond_day(jd)
        if timed:
            return schema.TimedWhen(at=self.local(jd), beyond_day=beyond)
        return schema.DatedWhen(date=self.local(jd).date(), beyond_day=beyond)


def _phase_name(elongation_start: float, elongation_end: float) -> str:
    quadrant_start = int(elongation_start // 90.0)
    quadrant_end = int(elongation_end // 90.0)
    if quadrant_start != quadrant_end:
        return _QUARTERS[quadrant_end]  # за сутки пройдена граница четверти
    return _BETWEEN[quadrant_start]


def _aspect_event(hit: AspectHit, clock: _Clock) -> schema.AspectEvent:
    return schema.AspectEvent(
        body_a=hit.body_a, body_b=hit.body_b, aspect=hit.aspect, when=clock.when(hit.jd, hit.timed)
    )


def _eclipse(lunation) -> schema.Eclipse | None:
    if lunation.eclipse is None:
        return None
    return schema.Eclipse(kind=lunation.eclipse.kind, type=lunation.eclipse.type)


def _moon(sky: DaySky, clock: _Clock) -> schema.Moon:
    phase = sky.moon_phase
    ingress = next((h for h in sky.ingresses if h.body is Body.MOON), None)
    return schema.Moon(
        phase=schema.MoonPhase(
            name=_phase_name(phase.elongation_start, phase.elongation_end),
            waxing=phase.elongation_start < 180.0,
            illumination_pct_start=round(phase.illumination_start * 100),
            illumination_pct_end=round(phase.illumination_end * 100),
        ),
        ingress=ingress and schema.MoonIngress(
            from_sign=ingress.from_sign, to_sign=ingress.to_sign, when=clock.when(ingress.jd)
        ),
        void_of_course=[
            schema.VoidOfCourse(
                start=clock.local(v.start_jd),
                end=clock.local(v.end_jd),
                starts_before_day=v.start_jd < sky.start_jd,
                ends_after_day=v.end_jd >= sky.end_jd,
                sign=v.sign,
                next_sign=v.next_sign,
                last_aspect=v.last_aspect and schema.LastAspect(
                    body=v.last_aspect.body_b if v.last_aspect.body_a is Body.MOON else v.last_aspect.body_a,
                    aspect=v.last_aspect.aspect,
                ),
            )
            for v in sky.void_of_course
        ],
        aspects=[_aspect_event(h, clock) for h in sky.aspects if Body.MOON in (h.body_a, h.body_b)],
    )


def _background(sky: DaySky) -> schema.Background:
    def sun(state) -> schema.SunPoint:
        return schema.SunPoint(sign=sign_of(state.longitude), degree=int(state.longitude % 30.0))

    def state(a) -> str:
        if a.exact_today:
            return "exact"
        return "applying" if a.orb_end < a.orb_start else "separating"

    return schema.Background(
        sun=schema.SunPosition(at_start=sun(sky.at_start[Body.SUN]), at_end=sun(sky.at_end[Body.SUN])),
        retrograde=[body for body, st in sky.at_start.items() if st.speed < 0],
        slow_aspects=[
            schema.SlowAspect(
                body_a=a.body_a, body_b=a.body_b, aspect=a.aspect, orb_deg=round(a.orb_start, 1), state=state(a)
            )
            for a in sky.slow_aspects
        ],
    )


def project(sky: DaySky, frame: Frame, focus: Body, clock: _Clock) -> schema.SignFacts:
    """Проекция неба суток на систему отсчёта. focus — тело, события которого помечаются
    (для знака это его управитель)."""

    def house_at(body: Body, jd: float) -> int:
        return frame.house_of(sky.trajectories[body].at(jd).longitude)

    today: list[tuple[float, schema.TodayEvent]] = []
    for h in sky.ingresses:
        entered = SIGN_ORDER.index(h.to_sign) * 30.0 + 15.0
        left = SIGN_ORDER.index(h.from_sign) * 30.0 + 15.0
        today.append((h.jd, schema.HouseIngressToday(
            body=h.body, from_house=frame.house_of(left), to_house=frame.house_of(entered),
            when=clock.when(h.jd), involves_ruler=h.body is focus,
        )))
    for h in sky.aspects:
        today.append((h.jd, schema.ExactAspectToday(
            body_a=h.body_a, house_a=house_at(h.body_a, h.jd),
            body_b=h.body_b, house_b=house_at(h.body_b, h.jd),
            aspect=h.aspect, when=clock.when(h.jd, h.timed), involves_ruler=focus in (h.body_a, h.body_b),
        )))
    for h in sky.stations:
        if h.jd < sky.lookahead_end_jd:
            today.append((h.jd, schema.StationToday(
                body=h.body, direction=h.direction, house=frame.house_of(h.longitude),
                when=clock.when(h.jd), involves_ruler=h.body is focus,
            )))
    for h in sky.lunations:
        today.append((h.jd, schema.LunationToday(
            lunation=h.kind, house=frame.house_of(h.moon_longitude), eclipse=_eclipse(h), when=clock.when(h.jd),
        )))
    today.sort(key=lambda item: item[0])

    start, end = sky.at_start[focus], sky.at_end[focus]
    return schema.SignFacts(
        houses=[
            schema.HousePlacement(
                body=body,
                house_at_start=frame.house_of(sky.at_start[body].longitude),
                house_at_end=frame.house_of(sky.at_end[body].longitude),
            )
            for body in sky.at_start
        ],
        ruler=schema.Ruler(
            body=focus,
            sign_at_start=sign_of(start.longitude),
            sign_at_end=sign_of(end.longitude),
            house_at_start=frame.house_of(start.longitude),
            house_at_end=frame.house_of(end.longitude),
            retrograde=start.speed < 0,
        ),
        today=[event for _, event in today],
    )


def build_day_facts(sky: DaySky, config: Config) -> schema.DayFacts:
    clock = _Clock(sky)
    return schema.DayFacts(
        schema_version=schema.SCHEMA_VERSION,
        meta=schema.Meta(
            date=sky.day,
            tz=sky.tz,
            day_start=clock.local(sky.start_jd),
            day_end=clock.local(sky.end_jd),
            day_length_hours=sky.length_hours,
            lookahead_hours=sky.lookahead_hours,
            config_hash=sky.config_hash,
            tzdata_version=tzdata_version(),
            service_version=__version__,
        ),
        bodies=[
            schema.BodyPosition(
                body=body,
                sign_at_start=sign_of(sky.at_start[body].longitude),
                sign_at_end=sign_of(sky.at_end[body].longitude),
                retrograde=sky.at_start[body].speed < 0,
            )
            for body in sky.at_start
        ],
        moon=_moon(sky, clock),
        exact_aspects=[_aspect_event(h, clock) for h in sky.aspects if Body.MOON not in (h.body_a, h.body_b)],
        ingresses=[
            schema.Ingress(
                body=h.body, from_sign=h.from_sign, to_sign=h.to_sign, retrograde=h.speed < 0, when=clock.when(h.jd)
            )
            for h in sky.ingresses if h.body is not Body.MOON
        ],
        stations=[
            schema.Station(
                body=h.body, direction=h.direction, sign=sign_of(h.longitude), when=clock.when(h.jd),
                days_ahead=(clock.local(h.jd).date() - sky.day).days,
            )
            for h in sky.stations
        ],
        lunations=[
            schema.Lunation(kind=h.kind, sign=sign_of(h.moon_longitude), when=clock.when(h.jd), eclipse=_eclipse(h))
            for h in sky.lunations
        ],
        background=_background(sky),
        signs={
            sign: project(sky, SolarSignFrame(sign), ruler_of(sign, config.rulers.scheme), clock)
            for sign in Sign
        },
    )
