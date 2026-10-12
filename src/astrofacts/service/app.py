"""HTTP-слой: GET /day и GET /health."""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from .. import __version__, ephemeris
from ..assemble import build_day_facts, tzdata_version
from ..config import Config, load_config
from ..schema import SCHEMA_VERSION, DayFacts, ErrorResponse
from ..sky import scan_day
from ..timeutil import UnknownTimezone, get_zone
from .cache import LruCache

# Файлы эфемерид покрывают 1800–2399; расчёту нужен запас в несколько суток по обе стороны.
MIN_DATE = dt.date(1800, 2, 1)
MAX_DATE = dt.date(2399, 11, 30)


def _error(status: int, code: str, detail: str, **extra) -> JSONResponse:
    body = ErrorResponse(error=code, detail=detail, **extra)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json", exclude_none=True))


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    cache = LruCache(config.cache.max_entries)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Без файлов эфемерид сервис не стартует: лучше отказ при запуске, чем на первом запросе.
        ephemeris.check_files()
        yield

    app = FastAPI(
        title="astrofacts",
        version=__version__,
        description=f"Астрономические факты суток. Версия схемы ответа: {SCHEMA_VERSION}.",
        lifespan=lifespan,
    )

    @app.get(
        "/day",
        response_model=DayFacts,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def day(
        date: str | None = Query(None, description="Дата, ГГГГ-ММ-ДД"),
        tz: str | None = Query(None, description="Таймзона IANA, например Europe/Moscow"),
        lookahead: str | None = Query(None, description="Окно опережения после конца суток, часы"),
        schema: str | None = Query(None, description="Версия схемы, которую ожидает потребитель"),
    ):
        if schema is not None and schema != str(SCHEMA_VERSION):
            return _error(
                409, "schema_version_mismatch",
                f"сервис отдаёт схему версии {SCHEMA_VERSION}, запрошена {schema!r}",
                supported_schema_versions=[SCHEMA_VERSION],
            )
        if not date or not tz:
            return _error(422, "missing_parameter", "обязательны параметры date и tz")
        try:
            day_ = dt.date.fromisoformat(date)
        except ValueError:
            return _error(422, "invalid_date", f"дата не разобрана: {date!r}, нужен формат ГГГГ-ММ-ДД")
        if not MIN_DATE <= day_ <= MAX_DATE:
            return _error(422, "date_out_of_range", f"дата вне диапазона эфемерид: {MIN_DATE} — {MAX_DATE}")
        try:
            get_zone(tz)
        except UnknownTimezone as e:
            return _error(422, "unknown_timezone", str(e))
        hours = config.lookahead.default_hours
        if lookahead is not None:
            try:
                hours = float(lookahead)
            except ValueError:
                return _error(422, "invalid_lookahead", f"lookahead не число: {lookahead!r}")
        if not 0 <= hours <= config.lookahead.max_hours:  # заодно отсекает NaN
            return _error(422, "invalid_lookahead", f"lookahead: допустимо от 0 до {config.lookahead.max_hours:g} часов")

        return cache.get_or_compute(
            (day_, tz, hours, config.hash),
            lambda: build_day_facts(scan_day(day_, tz, config, hours), config),
        )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "config_hash": config.hash,
            "tzdata_version": tzdata_version(),
            "cache": {"entries": len(cache), "hits": cache.hits, "misses": cache.misses},
        }

    return app
