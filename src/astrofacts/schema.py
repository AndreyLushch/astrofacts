"""Схема ответа сервиса. Это контракт с потребителями: JSON Schema отдаётся в /openapi.json.

Любое изменение, ломающее разбор у потребителя, увеличивает SCHEMA_VERSION.
В ответе нет абсолютных долгот: положение передаётся знаком и домом.
"""
from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .types import Aspect, Body, Sign

SCHEMA_VERSION = 1

House = Annotated[int, Field(ge=1, le=12)]
EclipseKind = Literal["solar", "lunar"]
EclipseType = Literal["total", "annular", "hybrid", "partial", "penumbral"]
LunationKind = Literal["new_moon", "full_moon"]
Direction = Literal["retrograde", "direct"]
PhaseName = Literal[
    "new_moon", "waxing_crescent", "first_quarter", "waxing_gibbous",
    "full_moon", "waning_gibbous", "last_quarter", "waning_crescent",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- момент события ---

class TimedWhen(Model):
    """Момент с точностью до минуты, в таймзоне запроса; секунды отброшены."""
    precision: Literal["minute"] = "minute"
    at: dt.datetime
    beyond_day: bool = Field(description="Событие в окне опережения, после конца суток")


class DatedWhen(Model):
    """Только дата: событие слишком медленное, чтобы называть его час."""
    precision: Literal["day"] = "day"
    date: dt.date
    beyond_day: bool


When = Annotated[Union[TimedWhen, DatedWhen], Field(discriminator="precision")]


# --- общая часть ---

class Meta(Model):
    date: dt.date
    tz: str
    day_start: dt.datetime
    day_end: dt.datetime = Field(description="Начало следующих суток; сутки — [day_start, day_end)")
    day_length_hours: float = Field(description="23, 24 или 25 при переводе часов")
    lookahead_hours: float
    config_hash: str
    tzdata_version: str
    service_version: str


class BodyPosition(Model):
    body: Body
    sign_at_start: Sign
    sign_at_end: Sign
    retrograde: bool = Field(description="Попятное движение на начало суток")


class AspectEvent(Model):
    body_a: Body
    body_b: Body
    aspect: Aspect
    when: When


class MoonPhase(Model):
    name: PhaseName = Field(description="Главная фаза называется только в сутки её точного момента")
    waxing: bool
    illumination_pct_start: int = Field(ge=0, le=100)
    illumination_pct_end: int = Field(ge=0, le=100)


class MoonIngress(Model):
    from_sign: Sign
    to_sign: Sign
    when: When


class LastAspect(Model):
    body: Body
    aspect: Aspect


class VoidOfCourse(Model):
    start: dt.datetime
    end: dt.datetime
    starts_before_day: bool
    ends_after_day: bool
    sign: Sign
    next_sign: Sign
    last_aspect: LastAspect | None = Field(
        description="null — Луна не сделала в знаке ни одного аспекта; интервал идёт с входа в знак"
    )


class Moon(Model):
    phase: MoonPhase
    ingress: MoonIngress | None
    void_of_course: list[VoidOfCourse]
    aspects: list[AspectEvent]


class Ingress(Model):
    body: Body
    from_sign: Sign
    to_sign: Sign
    retrograde: bool = Field(description="Вход в знак попятным движением")
    when: When


class Station(Model):
    body: Body
    direction: Direction = Field(description="Каким движение становится")
    sign: Sign
    when: When
    days_ahead: int = Field(ge=0, description="0 — в эти сутки")


class Eclipse(Model):
    kind: EclipseKind
    type: EclipseType


class Lunation(Model):
    kind: LunationKind
    sign: Sign = Field(description="Знак Луны")
    when: When
    eclipse: Eclipse | None


class SunPoint(Model):
    sign: Sign
    degree: int = Field(ge=0, le=29, description="Целый градус внутри знака")


class SunPosition(Model):
    at_start: SunPoint
    at_end: SunPoint


class SlowAspect(Model):
    body_a: Body
    body_b: Body
    aspect: Aspect
    orb_deg: float = Field(description="Отклонение от точного аспекта на начало суток, до 0,1°")
    state: Literal["applying", "exact", "separating"]


class Background(Model):
    sun: SunPosition
    retrograde: list[Body]
    slow_aspects: list[SlowAspect]


# --- проекция на знак ---

class HousePlacement(Model):
    body: Body
    house_at_start: House
    house_at_end: House


class Ruler(Model):
    body: Body
    sign_at_start: Sign
    sign_at_end: Sign
    house_at_start: House
    house_at_end: House
    retrograde: bool


class HouseIngressToday(Model):
    kind: Literal["house_ingress"] = "house_ingress"
    body: Body
    from_house: House
    to_house: House
    when: When
    involves_ruler: bool


class ExactAspectToday(Model):
    kind: Literal["exact_aspect"] = "exact_aspect"
    body_a: Body
    house_a: House
    body_b: Body
    house_b: House
    aspect: Aspect
    when: When
    involves_ruler: bool


class StationToday(Model):
    kind: Literal["station"] = "station"
    body: Body
    direction: Direction
    house: House
    when: When
    involves_ruler: bool


class LunationToday(Model):
    kind: Literal["lunation"] = "lunation"
    lunation: LunationKind
    house: House
    eclipse: Eclipse | None
    when: When


TodayEvent = Annotated[
    Union[HouseIngressToday, ExactAspectToday, StationToday, LunationToday],
    Field(discriminator="kind"),
]


class SignFacts(Model):
    houses: list[HousePlacement]
    ruler: Ruler
    today: list[TodayEvent] = Field(description="Только то, что случилось или стало точным в эти сутки")


class DayFacts(Model):
    schema_version: int
    meta: Meta
    bodies: list[BodyPosition]
    moon: Moon
    exact_aspects: list[AspectEvent] = Field(description="Без аспектов Луны: они в moon.aspects")
    ingresses: list[Ingress] = Field(description="Без Луны: её смена знака в moon.ingress")
    stations: list[Station]
    lunations: list[Lunation]
    background: Background
    signs: dict[Sign, SignFacts]


class ErrorResponse(Model):
    error: str
    detail: str
    supported_schema_versions: list[int] | None = None
