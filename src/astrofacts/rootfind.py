"""Поиск моментов, когда угловая функция времени проходит через заданное значение."""
from __future__ import annotations

from typing import Callable, Sequence

from .types import wrap180

# Точность момента: около 0,1 секунды.
TIME_TOLERANCE_DAYS = 1e-6


def bisect(f: Callable[[float], float], ta: float, fa: float, tb: float, fb: float) -> float:
    """Корень f на [ta, tb] при значениях разного знака на концах."""
    while tb - ta > TIME_TOLERANCE_DAYS:
        tm = 0.5 * (ta + tb)
        fm = f(tm)
        if fm == 0.0:
            return tm
        if (fa < 0.0) == (fm < 0.0):
            ta, fa = tm, fm
        else:
            tb, fb = tm, fm
    return 0.5 * (ta + tb)


def crossings(
    angle: Callable[[float], float],
    rate: Callable[[float], float],
    times: Sequence[float],
    angles: Sequence[float],
    rates: Sequence[float],
    target: float,
) -> list[float]:
    """Моменты, когда angle(t) ≡ target (mod 360), на отрезке, покрытом сеткой times.

    angles и rates — значения функции и её производной в узлах сетки. Если производная меняет
    знак внутри ячейки (станция, разворот взаимного движения), ячейка делится в точке экстремума:
    так находятся и два близких прохождения, между которыми функция едва переходит через цель.
    """
    found: list[float] = []

    def offset(t: float) -> float:
        return wrap180(angle(t) - target)

    def scan(ta: float, fa: float, tb: float, fb: float) -> None:
        # Скачок через ±180 — не прохождение через цель, а разрыв свёртки угла.
        if abs(fa) >= 90.0 or abs(fb) >= 90.0:
            return
        if fa == 0.0:
            found.append(ta)
        elif fb != 0.0 and (fa < 0.0) != (fb < 0.0):
            found.append(bisect(offset, ta, fa, tb, fb))

    for i in range(len(times) - 1):
        ta, tb = times[i], times[i + 1]
        fa, fb = wrap180(angles[i] - target), wrap180(angles[i + 1] - target)
        ra, rb = rates[i], rates[i + 1]
        if ra != 0.0 and rb != 0.0 and (ra < 0.0) != (rb < 0.0):
            tm = bisect(rate, ta, ra, tb, rb)
            fm = offset(tm)
            scan(ta, fa, tm, fm)
            scan(tm, fm, tb, fb)
        else:
            scan(ta, fa, tb, fb)
    return found


def sign_changes(
    f: Callable[[float], float], times: Sequence[float], values: Sequence[float]
) -> list[tuple[float, bool]]:
    """Нули f на сетке: (момент, True если значение перешло из плюса в минус)."""
    found: list[tuple[float, bool]] = []
    for i in range(len(times) - 1):
        fa, fb = values[i], values[i + 1]
        if fa == 0.0:
            if i > 0 and values[i - 1] != 0.0 and fb != 0.0 and (values[i - 1] < 0.0) != (fb < 0.0):
                found.append((times[i], values[i - 1] > 0.0))
        elif fb != 0.0 and (fa < 0.0) != (fb < 0.0):
            found.append((bisect(f, times[i], fa, times[i + 1], fb), fa > 0.0))
    return found
