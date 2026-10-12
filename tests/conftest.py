from __future__ import annotations

import os
from pathlib import Path

import pytest

from astrofacts.config import load_config



def pytest_sessionstart(session):
    from astrofacts import ephemeris

    try:
        ephemeris.check_files()
    except ephemeris.EphemerisError as e:
        pytest.exit(f"тесты не запущены: {e}", returncode=2)


KERNEL = Path(__file__).parent / "data" / "de432s.bsp"


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def reference():
    """Независимый расчёт видимой эклиптической долготы: astropy/ERFA по ядру JPL."""
    # Полный набор (scripts/dev.sh test-full) пропусков не допускает: без него релиз на dev не собирается.
    required = os.environ.get("ASTROFACTS_REQUIRE_REFERENCE") == "1"
    problem = None
    if not KERNEL.exists():
        problem = "нет ядра JPL для сверки: выполните `python tools/fetch_reference_kernel.py`"
    else:
        try:
            import jplephem  # noqa: F401
            from astropy import coordinates
        except ImportError as e:
            problem = f"для сверочных тестов нужны astropy и jplephem: {e}"
    if problem:
        if required:
            pytest.fail(problem, pytrace=False)
        pytest.skip(problem)
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False  # тесты работают без сети
    coordinates.solar_system_ephemeris.set(str(KERNEL))

    def longitude(body, jd: float) -> float:
        moment = Time(jd, format="jd", scale="ut1")
        frame = coordinates.GeocentricTrueEcliptic(equinox=moment, obstime=moment)
        return float(coordinates.get_body(body.value, moment).transform_to(frame).lon.deg)

    return longitude
