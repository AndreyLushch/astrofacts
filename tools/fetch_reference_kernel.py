"""Загрузка ядра JPL DE432s для сверочных тестов (tests/data/de432s.bsp, в git не хранится).

    python tools/fetch_reference_kernel.py

Ядро нужно только тестам: по нему astropy считает положения тел независимо от Swiss Ephemeris.
Контрольная сумма сверена с копией того же файла в архиве Software Heritage.
"""
from __future__ import annotations

import sys
from pathlib import Path

from _fetch import fetch

URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de432s.bsp"
SHA256 = "363f32e14f5255359ac32c4d38080cf28ab55564a5e16696a75f63394b666e9b"
TARGET = Path(__file__).resolve().parent.parent / "tests" / "data" / "de432s.bsp"

if __name__ == "__main__":
    sys.exit(0 if fetch(URL, TARGET, SHA256) else 1)
