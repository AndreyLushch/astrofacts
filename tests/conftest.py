from __future__ import annotations

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
    if not KERNEL.exists():
        pytest.skip("нет ядра JPL для сверки: выполните `python tools/fetch_reference_kernel.py`")
    pytest.importorskip("jplephem")
    coordinates = pytest.importorskip("astropy.coordinates")
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False  # тесты работают без сети
    coordinates.solar_system_ephemeris.set(str(KERNEL))

    def longitude(body, jd: float) -> float:
        moment = Time(jd, format="jd", scale="ut1")
        frame = coordinates.GeocentricTrueEcliptic(equinox=moment, obstime=moment)
        return float(coordinates.get_body(body.value, moment).transform_to(frame).lon.deg)

    return longitude
