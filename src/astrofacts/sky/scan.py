"""Шаг первый: сканирование суток и построение DaySky."""
from __future__ import annotations

import math
from datetime import date, timedelta
from itertools import combinations

from .. import ephemeris
from ..config import Config
from ..timeutil import day_interval, get_zone, local_midnight
from ..types import ASPECT_ANGLE, Aspect, Body, wrap180
from .events import find_aspects, find_ingresses, find_stations
from .model import DaySky, LunationHit, MoonPhase, SlowAspect, Trajectory
from .moon import void_of_course

GRID_STEP_DAYS = 1.0 / 24.0
# Луна проходит знак не дольше 2,8 суток; запас по обе стороны нужен, чтобы у каждого
# пребывания Луны в знаке, задевающего сутки, были известны и вход, и выход.
MOON_MARGIN_DAYS = 3.0


def _trajectory(body: Body, times: tuple[float, ...]) -> Trajectory:
    longitudes: list[float] = []
    speeds: list[float] = []
    for jd in times:
        st = ephemeris.state(body, jd)
        lon = st.longitude
        if longitudes:
            lon = longitudes[-1] + wrap180(lon - longitudes[-1])
        longitudes.append(lon)
        speeds.append(st.speed)
    return Trajectory(times, tuple(longitudes), tuple(speeds))


def _orb(lon_a: float, lon_b: float, aspect: Aspect) -> float:
    angle = ASPECT_ANGLE[aspect]
    return min(abs(wrap180(lon_a - lon_b - angle)), abs(wrap180(lon_a - lon_b + angle)))


def scan_day(day: date, tz: str, config: Config, lookahead_hours: float | None = None) -> DaySky:
    """Небо локальных суток: траектории тел и события с точными моментами."""
    if lookahead_hours is None:
        lookahead_hours = config.lookahead.default_hours
    if not 0 <= lookahead_hours <= config.lookahead.max_hours:
        raise ValueError(f"lookahead: допустимо от 0 до {config.lookahead.max_hours:g} часов")

    zone = get_zone(tz)
    interval = day_interval(day, zone)
    start = ephemeris.jd_from_datetime(interval.start)
    end = ephemeris.jd_from_datetime(interval.end)
    window_end = end + lookahead_hours / 24.0
    stations_end = ephemeris.jd_from_datetime(
        local_midnight(day + timedelta(days=config.stations.window_days + 1), zone)
    )

    grid_from = start - MOON_MARGIN_DAYS
    grid_to = max(window_end + MOON_MARGIN_DAYS, stations_end)
    steps = math.ceil((grid_to - grid_from) / GRID_STEP_DAYS)
    times = tuple(grid_from + i * GRID_STEP_DAYS for i in range(steps + 1))
    trajectories = {body: _trajectory(body, times) for body in config.bodies}

    def in_window(jd: float) -> bool:
        return start <= jd < window_end

    enabled = config.aspects.enabled
    voc = config.void_of_course
    all_aspects = find_aspects(
        trajectories, combinations(config.bodies, 2), tuple(dict.fromkeys((*enabled, *voc.aspects))), config
    )
    ingresses = find_ingresses(trajectories)

    moon_aspects = [h for h in all_aspects if Body.MOON in (h.body_a, h.body_b)]
    moon_ingresses = [h for h in ingresses if h.body is Body.MOON]
    voc_intervals = [
        v for v in void_of_course(moon_ingresses, moon_aspects, voc.bodies, voc.aspects)
        if v.start_jd < window_end and v.end_jd > start
    ]

    day_aspects = [h for h in all_aspects if h.aspect in enabled and in_window(h.jd)]

    lunations: list[LunationHit] = []
    for h in day_aspects:
        if (h.body_a, h.body_b) != (Body.SUN, Body.MOON):
            continue
        if h.aspect not in (Aspect.CONJUNCTION, Aspect.OPPOSITION):
            continue
        full = h.aspect is Aspect.OPPOSITION
        lunations.append(LunationHit(
            "full_moon" if full else "new_moon", h.jd,
            ephemeris.state(Body.MOON, h.jd).longitude,
            ephemeris.eclipse_near(h.jd, lunar=full),
        ))

    at_start = {body: ephemeris.state(body, start) for body in config.bodies}
    at_end = {body: ephemeris.state(body, end) for body in config.bodies}

    slow_aspects: list[SlowAspect] = []
    slow = [b for b in config.bodies if config.is_slow(b)]
    for a, b in combinations(slow, 2):
        for aspect in enabled:
            orb_start = _orb(at_start[a].longitude, at_start[b].longitude, aspect)
            orb_end = _orb(at_end[a].longitude, at_end[b].longitude, aspect)
            exact = any(
                (h.body_a, h.body_b, h.aspect) == (a, b, aspect) and start <= h.jd < end
                for h in day_aspects
            )
            if exact or min(orb_start, orb_end) <= config.orbs.background[aspect]:
                slow_aspects.append(SlowAspect(a, b, aspect, orb_start, orb_end, exact))

    return DaySky(
        day=day,
        tz=tz,
        start_jd=start,
        end_jd=end,
        lookahead_end_jd=window_end,
        lookahead_hours=lookahead_hours,
        length_hours=interval.length_hours,
        config_hash=config.hash,
        trajectories=trajectories,
        at_start=at_start,
        at_end=at_end,
        aspects=tuple(day_aspects),
        ingresses=tuple(h for h in ingresses if in_window(h.jd)),
        lunations=tuple(lunations),
        void_of_course=tuple(voc_intervals),
        stations=tuple(h for h in find_stations(trajectories) if start <= h.jd < stations_end),
        moon_phase=MoonPhase(
            elongation_start=(at_start[Body.MOON].longitude - at_start[Body.SUN].longitude) % 360.0,
            elongation_end=(at_end[Body.MOON].longitude - at_end[Body.SUN].longitude) % 360.0,
            illumination_start=ephemeris.moon_illumination(start),
            illumination_end=ephemeris.moon_illumination(end),
        ),
        slow_aspects=tuple(slow_aspects),
    )
