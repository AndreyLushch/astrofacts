"""Единственный модуль, обращающийся к Swiss Ephemeris.

Наружу отдаются собственные типы и числа; время — юлианская дата в UT.
Положения — видимые геоцентрические, эклиптика и равноденствие даты (тропический зодиак).
Эфемериды читаются из файлов .se1. В репозитории и дистрибутиве их нет: они загружаются
при развёртывании (tools/fetch_ephemeris.py). Без файлов модуль отказывается работать;
сам он ничего не скачивает, а подмена на встроенную аналитическую модель считается ошибкой.
"""
from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

import swisseph as swe

from .types import Body

_UNIX_EPOCH_JD = 2440587.5
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_SWE_BODY = {
    Body.SUN: swe.SUN,
    Body.MOON: swe.MOON,
    Body.MERCURY: swe.MERCURY,
    Body.VENUS: swe.VENUS,
    Body.MARS: swe.MARS,
    Body.JUPITER: swe.JUPITER,
    Body.SATURN: swe.SATURN,
    Body.URANUS: swe.URANUS,
    Body.NEPTUNE: swe.NEPTUNE,
    Body.PLUTO: swe.PLUTO,
}
_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

# Библиотека хранит состояние в глобальных переменных и не рассчитана на параллельные вызовы.
_lock = threading.RLock()
_ready = False


EPHE_ENV = "ASTROFACTS_EPHE_DIR"
# Планеты и Луна, 1800–2399. Контрольные суммы — файлов из официального репозитория
# https://github.com/aloistr/swisseph (каталог ephe/).
REQUIRED_FILES = {
    "sepl_18.se1": "ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66",
    "semo_18.se1": "1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7",
}


class EphemerisError(RuntimeError):
    pass


def ephe_dir() -> Path:
    """Каталог файлов эфемерид: ASTROFACTS_EPHE_DIR, иначе data/ephe внутри пакета."""
    configured = os.environ.get(EPHE_ENV)
    return Path(configured) if configured else Path(str(resources.files("astrofacts").joinpath("data/ephe")))


def check_files() -> Path:
    """Проверяет, что файлы эфемерид на месте и не повреждены. Возвращает их каталог."""
    directory = ephe_dir()
    for name, expected in REQUIRED_FILES.items():
        path = directory / name
        if not path.is_file():
            raise EphemerisError(
                f"нет файла эфемерид {path}. Файлы загружаются при развёртывании: "
                f"python tools/fetch_ephemeris.py; каталог задаётся переменной {EPHE_ENV}"
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise EphemerisError(f"файл эфемерид {path} повреждён или не той версии: контрольная сумма не совпала")
    return directory


@dataclass(frozen=True, slots=True)
class BodyState:
    longitude: float  # градусы, [0, 360)
    speed: float      # градусов в сутки, отрицательная при попятном движении


@dataclass(frozen=True, slots=True)
class Eclipse:
    kind: str     # solar | lunar
    type: str     # total | annular | hybrid | partial | penumbral
    max_jd: float


def _ensure_ready() -> None:
    global _ready
    if not _ready:
        swe.set_ephe_path(str(check_files()))
        _ready = True


def jd_from_datetime(moment: datetime) -> float:
    if moment.tzinfo is None:
        raise ValueError("нужен момент времени с таймзоной")
    return _UNIX_EPOCH_JD + (moment - _EPOCH) / timedelta(days=1)


def datetime_from_jd(jd: float) -> datetime:
    return _EPOCH + timedelta(days=jd - _UNIX_EPOCH_JD)


def state(body: Body, jd: float) -> BodyState:
    with _lock:
        _ensure_ready()
        try:
            values, used = swe.calc_ut(jd, _SWE_BODY[body], _FLAGS)
        except swe.Error as e:
            raise EphemerisError(f"{body.value}, JD {jd:.5f}: {e}") from e
    if not used & swe.FLG_SWIEPH:
        raise EphemerisError(f"{body.value}, JD {jd:.5f}: файлы эфемерид не использованы")
    return BodyState(values[0] % 360.0, values[3])


def moon_illumination(jd: float) -> float:
    """Освещённая доля диска Луны, 0..1."""
    with _lock:
        _ensure_ready()
        try:
            return swe.pheno_ut(jd, swe.MOON, swe.FLG_SWIEPH)[1]
        except swe.Error as e:
            raise EphemerisError(f"освещённость Луны, JD {jd:.5f}: {e}") from e


def _eclipse_type(flags: int, lunar: bool) -> str:
    if not lunar and flags & swe.ECL_ANNULAR_TOTAL:
        return "hybrid"
    if flags & swe.ECL_TOTAL:
        return "total"
    if not lunar and flags & swe.ECL_ANNULAR:
        return "annular"
    if flags & swe.ECL_PARTIAL:
        return "partial"
    if lunar and flags & swe.ECL_PENUMBRAL:
        return "penumbral"
    raise EphemerisError(f"неизвестный тип затмения: флаги {flags}")


def eclipse_near(jd: float, lunar: bool, window_days: float = 1.0) -> Eclipse | None:
    """Затмение (где-либо на Земле), максимум которого отстоит от момента не дальше окна."""
    with _lock:
        _ensure_ready()
        try:
            if lunar:
                flags, times = swe.lun_eclipse_when(jd - window_days, swe.FLG_SWIEPH)
            else:
                flags, times = swe.sol_eclipse_when_glob(jd - window_days, swe.FLG_SWIEPH)
        except swe.Error as e:
            raise EphemerisError(f"поиск затмения, JD {jd:.5f}: {e}") from e
    if abs(times[0] - jd) > window_days:
        return None
    return Eclipse("lunar" if lunar else "solar", _eclipse_type(flags, lunar), times[0])
