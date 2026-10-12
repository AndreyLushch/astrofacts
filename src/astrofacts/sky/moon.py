"""Луна: интервалы без курса."""
from __future__ import annotations

from typing import Sequence

from ..types import Aspect, Body
from .model import AspectHit, IngressHit, VoidOfCourse


def void_of_course(
    moon_ingresses: Sequence[IngressHit],
    moon_aspects: Sequence[AspectHit],
    bodies: Sequence[Body],
    aspects: Sequence[Aspect],
) -> list[VoidOfCourse]:
    """Интервалы без курса для каждого полного пребывания Луны в знаке.

    Пребывание полное, если известны и вход в знак, и выход из него: только тогда известно,
    что последний найденный аспект действительно последний.
    """
    counted = [
        h for h in moon_aspects
        if h.aspect in aspects and (h.body_b if h.body_a is Body.MOON else h.body_a) in bodies
    ]
    result: list[VoidOfCourse] = []
    for entry, leave in zip(moon_ingresses, moon_ingresses[1:]):
        inside = [h for h in counted if entry.jd <= h.jd < leave.jd]
        last = inside[-1] if inside else None
        result.append(VoidOfCourse(
            start_jd=last.jd if last else entry.jd,
            end_jd=leave.jd,
            sign=entry.to_sign,
            next_sign=leave.to_sign,
            last_aspect=last,
        ))
    return result
