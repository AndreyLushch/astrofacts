"""Управители знаков."""
from __future__ import annotations

from .types import Body, Sign

_TRADITIONAL: dict[Sign, Body] = {
    Sign.ARIES: Body.MARS,
    Sign.TAURUS: Body.VENUS,
    Sign.GEMINI: Body.MERCURY,
    Sign.CANCER: Body.MOON,
    Sign.LEO: Body.SUN,
    Sign.VIRGO: Body.MERCURY,
    Sign.LIBRA: Body.VENUS,
    Sign.SCORPIO: Body.MARS,
    Sign.SAGITTARIUS: Body.JUPITER,
    Sign.CAPRICORN: Body.SATURN,
    Sign.AQUARIUS: Body.SATURN,
    Sign.PISCES: Body.JUPITER,
}
_MODERN = {**_TRADITIONAL, Sign.SCORPIO: Body.PLUTO, Sign.AQUARIUS: Body.URANUS, Sign.PISCES: Body.NEPTUNE}


def ruler_of(sign: Sign, scheme: str) -> Body:
    return (_MODERN if scheme == "modern" else _TRADITIONAL)[sign]
