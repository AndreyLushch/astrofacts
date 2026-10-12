"""Поиск событий на сетке: точные аспекты, ингрессии, станции."""
from __future__ import annotations

from typing import Iterable, Sequence

from .. import ephemeris
from ..config import Config
from ..rootfind import crossings, sign_changes
from ..types import ASPECT_ANGLE, BODY_ORDER, SIGN_ORDER, Aspect, Body
from .model import AspectHit, IngressHit, StationHit, Trajectory


def ordered_pair(a: Body, b: Body) -> tuple[Body, Body]:
    return (a, b) if BODY_ORDER.index(a) < BODY_ORDER.index(b) else (b, a)


def _targets(aspect: Aspect) -> tuple[float, ...]:
    angle = ASPECT_ANGLE[aspect]
    return (angle,) if angle in (0.0, 180.0) else (angle, -angle)


def find_aspects(
    trajectories: dict[Body, Trajectory],
    pairs: Iterable[tuple[Body, Body]],
    aspects: Sequence[Aspect],
    config: Config,
) -> list[AspectHit]:
    """Все моменты точности заданных аспектов в заданных парах на всей сетке."""
    hits: list[AspectHit] = []
    for a, b in pairs:
        a, b = ordered_pair(a, b)
        ta, tb = trajectories[a], trajectories[b]
        separation = [x - y for x, y in zip(ta.longitudes, tb.longitudes)]
        rates = [x - y for x, y in zip(ta.speeds, tb.speeds)]

        def angle(jd: float, a=a, b=b) -> float:
            return ephemeris.state(a, jd).longitude - ephemeris.state(b, jd).longitude

        def rate(jd: float, a=a, b=b) -> float:
            return ephemeris.state(a, jd).speed - ephemeris.state(b, jd).speed

        for aspect in aspects:
            for target in _targets(aspect):
                for jd in crossings(angle, rate, ta.times, separation, rates, target):
                    speed = abs(rate(jd))
                    hits.append(AspectHit(a, b, aspect, jd, speed, config.is_timed(speed)))
    hits.sort(key=lambda h: h.jd)
    return hits


def find_ingresses(trajectories: dict[Body, Trajectory]) -> list[IngressHit]:
    hits: list[IngressHit] = []
    for body, tr in trajectories.items():

        def angle(jd: float, body=body) -> float:
            return ephemeris.state(body, jd).longitude

        def rate(jd: float, body=body) -> float:
            return ephemeris.state(body, jd).speed

        for index in range(12):
            for jd in crossings(angle, rate, tr.times, tr.longitudes, tr.speeds, 30.0 * index):
                speed = rate(jd)
                if speed == 0.0:
                    continue  # касание границы знака без перехода
                entered = SIGN_ORDER[index] if speed > 0 else SIGN_ORDER[index - 1]
                left = SIGN_ORDER[index - 1] if speed > 0 else SIGN_ORDER[index]
                hits.append(IngressHit(body, left, entered, jd, speed))
    hits.sort(key=lambda h: h.jd)
    return hits


def find_stations(trajectories: dict[Body, Trajectory]) -> list[StationHit]:
    hits: list[StationHit] = []
    for body, tr in trajectories.items():
        if body in (Body.SUN, Body.MOON):
            continue

        def speed(jd: float, body=body) -> float:
            return ephemeris.state(body, jd).speed

        for jd, falling in sign_changes(speed, tr.times, tr.speeds):
            hits.append(StationHit(
                body, "retrograde" if falling else "direct", jd,
                ephemeris.state(body, jd).longitude,
            ))
    hits.sort(key=lambda h: h.jd)
    return hits
