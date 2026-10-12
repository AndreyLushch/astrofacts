"""Собственные типы расчётного слоя. swisseph здесь не используется."""
from __future__ import annotations

from enum import Enum


class Body(str, Enum):
    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    URANUS = "uranus"
    NEPTUNE = "neptune"
    PLUTO = "pluto"


BODY_ORDER: tuple[Body, ...] = tuple(Body)

# Средняя геоцентрическая скорость по долготе, градусов в сутки. Нужна, чтобы отнести тело
# к «медленным» по порогу из конфигурации; мгновенная скорость для этого не годится
# (у станции она нулевая у любой планеты).
MEAN_SPEED: dict[Body, float] = {
    Body.SUN: 0.9856,
    Body.MOON: 13.1764,
    Body.MERCURY: 0.9856,
    Body.VENUS: 0.9856,
    Body.MARS: 0.5240,
    Body.JUPITER: 0.0831,
    Body.SATURN: 0.0335,
    Body.URANUS: 0.0117,
    Body.NEPTUNE: 0.0060,
    Body.PLUTO: 0.0040,
}


class Sign(str, Enum):
    ARIES = "aries"
    TAURUS = "taurus"
    GEMINI = "gemini"
    CANCER = "cancer"
    LEO = "leo"
    VIRGO = "virgo"
    LIBRA = "libra"
    SCORPIO = "scorpio"
    SAGITTARIUS = "sagittarius"
    CAPRICORN = "capricorn"
    AQUARIUS = "aquarius"
    PISCES = "pisces"


SIGN_ORDER: tuple[Sign, ...] = tuple(Sign)


class Aspect(str, Enum):
    CONJUNCTION = "conjunction"
    SEXTILE = "sextile"
    SQUARE = "square"
    TRINE = "trine"
    OPPOSITION = "opposition"
    SEMISEXTILE = "semisextile"
    SEMISQUARE = "semisquare"
    SESQUIQUADRATE = "sesquiquadrate"
    QUINCUNX = "quincunx"


ASPECT_ANGLE: dict[Aspect, float] = {
    Aspect.CONJUNCTION: 0.0,
    Aspect.SEXTILE: 60.0,
    Aspect.SQUARE: 90.0,
    Aspect.TRINE: 120.0,
    Aspect.OPPOSITION: 180.0,
    Aspect.SEMISEXTILE: 30.0,
    Aspect.SEMISQUARE: 45.0,
    Aspect.SESQUIQUADRATE: 135.0,
    Aspect.QUINCUNX: 150.0,
}

MAJOR_ASPECTS: tuple[Aspect, ...] = (
    Aspect.CONJUNCTION, Aspect.SEXTILE, Aspect.SQUARE, Aspect.TRINE, Aspect.OPPOSITION,
)


def wrap180(angle: float) -> float:
    """Угол в полуинтервале [-180, 180)."""
    return (angle + 180.0) % 360.0 - 180.0


def sign_of(longitude: float) -> Sign:
    return SIGN_ORDER[int((longitude % 360.0) // 30.0)]
