"""DaySky — «небо суток»: общая часть расчёта, не зависящая от системы отсчёта.

Внутренний тип: здесь точные долготы и моменты в юлианских датах (UT). В ответ сервиса
они в таком виде не попадают — этим занимается сборка DayFacts.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date

from ..ephemeris import BodyState, Eclipse
from ..types import Aspect, Body, Sign


@dataclass(frozen=True, slots=True)
class Trajectory:
    """Движение тела на сетке моментов; между узлами — кубическая интерполяция Эрмита.

    Проекции (в том числе будущая натальная) ищут по ней свои события, не обращаясь
    к эфемеридам повторно.
    """
    times: tuple[float, ...]
    longitudes: tuple[float, ...]  # развёрнутые: без скачка 360 -> 0
    speeds: tuple[float, ...]

    def at(self, jd: float) -> BodyState:
        if not self.times[0] <= jd <= self.times[-1]:
            raise ValueError("момент вне рассчитанного интервала")
        i = min(bisect_right(self.times, jd) - 1, len(self.times) - 2)
        h = self.times[i + 1] - self.times[i]
        s = (jd - self.times[i]) / h
        p0, p1 = self.longitudes[i], self.longitudes[i + 1]
        m0, m1 = self.speeds[i] * h, self.speeds[i + 1] * h
        s2, s3 = s * s, s * s * s
        lon = (2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * m0 + (-2 * s3 + 3 * s2) * p1 + (s3 - s2) * m1
        dlon = (6 * s2 - 6 * s) * p0 + (3 * s2 - 4 * s + 1) * m0 + (-6 * s2 + 6 * s) * p1 + (3 * s2 - 2 * s) * m1
        return BodyState(lon % 360.0, dlon / h)


@dataclass(frozen=True, slots=True)
class AspectHit:
    """Аспект стал точным. body_a раньше body_b в порядке тел."""
    body_a: Body
    body_b: Body
    aspect: Aspect
    jd: float
    relative_speed: float  # градусов в сутки в момент точности, по модулю
    timed: bool            # скорость не ниже порога: момент отдаётся с временем


@dataclass(frozen=True, slots=True)
class IngressHit:
    body: Body
    from_sign: Sign
    to_sign: Sign
    jd: float
    speed: float           # со знаком: отрицательная — вход попятным движением


@dataclass(frozen=True, slots=True)
class StationHit:
    body: Body
    direction: str         # retrograde | direct — каким движение становится
    jd: float
    longitude: float


@dataclass(frozen=True, slots=True)
class LunationHit:
    kind: str              # new_moon | full_moon
    jd: float
    moon_longitude: float
    eclipse: Eclipse | None


@dataclass(frozen=True, slots=True)
class VoidOfCourse:
    """Луна без курса: от последнего аспекта в знаке до входа в следующий знак."""
    start_jd: float
    end_jd: float
    sign: Sign
    next_sign: Sign
    # None — за всё пребывание в знаке Луна не сделала ни одного аспекта; интервал
    # начинается с входа в знак.
    last_aspect: AspectHit | None


@dataclass(frozen=True, slots=True)
class MoonPhase:
    elongation_start: float     # Луна минус Солнце по долготе, [0, 360)
    elongation_end: float
    illumination_start: float   # 0..1
    illumination_end: float


@dataclass(frozen=True, slots=True)
class SlowAspect:
    """Аспект двух медленных планет в орбе — фон, а не событие суток."""
    body_a: Body
    body_b: Body
    aspect: Aspect
    orb_start: float
    orb_end: float
    exact_today: bool


@dataclass(frozen=True, slots=True)
class DaySky:
    day: date
    tz: str
    start_jd: float            # начало локальных суток
    end_jd: float              # начало следующих суток; сутки — [start_jd, end_jd)
    lookahead_end_jd: float    # конец окна опережения; равен end_jd при нулевом окне
    lookahead_hours: float
    length_hours: float        # длина локальных суток: 23, 24 или 25 при переводе часов
    config_hash: str
    trajectories: dict[Body, Trajectory]
    at_start: dict[Body, BodyState]
    at_end: dict[Body, BodyState]
    # События в [start_jd, lookahead_end_jd), по времени. Случившееся в [end_jd, …) — за границей суток.
    aspects: tuple[AspectHit, ...]
    ingresses: tuple[IngressHit, ...]
    lunations: tuple[LunationHit, ...]
    # Интервалы, пересекающиеся с [start_jd, lookahead_end_jd).
    void_of_course: tuple[VoidOfCourse, ...]
    # Станции от начала суток до конца окна из конфигурации.
    stations: tuple[StationHit, ...]
    moon_phase: MoonPhase
    slow_aspects: tuple[SlowAspect, ...]

    def beyond_day(self, jd: float) -> bool:
        return jd >= self.end_jd
