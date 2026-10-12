"""Загрузка файлов Swiss Ephemeris (.se1) из официального репозитория Astrodienst.

    python tools/fetch_ephemeris.py [каталог]

Шаг развёртывания: сервис сам ничего не скачивает и без файлов не запускается.
Каталог по умолчанию — тот, где их ищет сервис (ASTROFACTS_EPHE_DIR, иначе каталог в пакете).
Файлы берутся из зафиксированного коммита и проверяются по контрольной сумме.
"""
from __future__ import annotations

import sys
from pathlib import Path

from _fetch import fetch

from astrofacts.ephemeris import REQUIRED_FILES, ephe_dir

# https://github.com/aloistr/swisseph, состояние ветки master на 2026-10-01
COMMIT = "aacf962d19d79f8bc921dbcdaacf306d85be1917"
BASE_URL = f"https://raw.githubusercontent.com/aloistr/swisseph/{COMMIT}/ephe"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ephe_dir()
    ok = True
    for name, checksum in REQUIRED_FILES.items():
        ok = fetch(f"{BASE_URL}/{name}", target / name, checksum) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
