"""Системы отсчёта для проекции неба суток."""
from .base import Frame
from .solar_sign import SolarSignFrame

__all__ = ["Frame", "SolarSignFrame"]
