"""Солярные дома: знак принят за первый дом, дома равны знакам (whole sign)."""
from __future__ import annotations

from dataclasses import dataclass

from ..types import SIGN_ORDER, Sign


@dataclass(frozen=True, slots=True)
class SolarSignFrame:
    sign: Sign

    def house_of(self, longitude: float) -> int:
        return (int((longitude % 360.0) // 30.0) - SIGN_ORDER.index(self.sign)) % 12 + 1
