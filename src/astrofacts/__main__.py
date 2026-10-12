"""Запуск сервиса: python -m astrofacts"""
from __future__ import annotations

import os
import sys

import uvicorn

from . import ephemeris
from .service import create_app


def main() -> int:
    try:
        ephemeris.check_files()
    except ephemeris.EphemerisError as e:
        print(f"astrofacts не запущен: {e}", file=sys.stderr)
        return 1
    uvicorn.run(
        create_app(),
        host=os.environ.get("ASTROFACTS_HOST", "127.0.0.1"),
        port=int(os.environ.get("ASTROFACTS_PORT", "8765")),
        log_level=os.environ.get("ASTROFACTS_LOG_LEVEL", "info"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
