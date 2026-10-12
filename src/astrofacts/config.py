"""Конфигурация расчёта: загрузка, проверка, хэш."""
from __future__ import annotations

import hashlib
import json
import os
import tomllib
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .types import MEAN_SPEED, Aspect, Body

CONFIG_ENV = "ASTROFACTS_CONFIG"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AspectsConfig(_Section):
    enabled: tuple[Aspect, ...]


class OrbsConfig(_Section):
    background: dict[Aspect, float]


class SpeedConfig(_Section):
    slow_threshold_deg_per_day: float = Field(gt=0)


class VoidOfCourseConfig(_Section):
    bodies: tuple[Body, ...]
    aspects: tuple[Aspect, ...]


class StationsConfig(_Section):
    window_days: int = Field(ge=0, le=30)


class LookaheadConfig(_Section):
    default_hours: float = Field(ge=0)
    max_hours: float = Field(ge=0, le=48)


class RulersConfig(_Section):
    scheme: Literal["modern", "traditional"]


class CacheConfig(_Section):
    max_entries: int = Field(ge=1)


class Config(_Section):
    bodies: tuple[Body, ...]
    aspects: AspectsConfig
    orbs: OrbsConfig
    speed: SpeedConfig
    void_of_course: VoidOfCourseConfig
    stations: StationsConfig
    lookahead: LookaheadConfig
    rulers: RulersConfig
    cache: CacheConfig

    @model_validator(mode="after")
    def _check(self) -> "Config":
        if Body.SUN not in self.bodies or Body.MOON not in self.bodies:
            raise ValueError("bodies: Солнце и Луна обязательны")
        if len(set(self.bodies)) != len(self.bodies):
            raise ValueError("bodies: повторы в списке")
        missing = [a.value for a in self.aspects.enabled if a not in self.orbs.background]
        if missing:
            raise ValueError(f"orbs.background: нет орба для {', '.join(missing)}")
        if self.lookahead.default_hours > self.lookahead.max_hours:
            raise ValueError("lookahead: default_hours больше max_hours")
        return self

    @cached_property
    def hash(self) -> str:
        """Хэш действующих значений, а не байтов файла: комментарии и порядок ключей не влияют."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def is_slow(self, body: Body) -> bool:
        return MEAN_SPEED[body] < self.speed.slow_threshold_deg_per_day

    def is_timed(self, speed_deg_per_day: float) -> bool:
        """Достаточно ли взаимной скорости пары, чтобы отдавать аспект с временем, а не датой."""
        return abs(speed_deg_per_day) >= self.speed.slow_threshold_deg_per_day


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Конфигурация из файла; без пути — из ASTROFACTS_CONFIG, иначе встроенная."""
    path = path or os.environ.get(CONFIG_ENV) or None
    if path:
        raw = Path(path).read_bytes()
    else:
        raw = resources.files("astrofacts").joinpath("data/default.toml").read_bytes()
    return Config.model_validate(tomllib.loads(raw.decode("utf-8")))
