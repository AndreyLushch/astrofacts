"""Кеш готовых ответов в памяти процесса."""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Callable, Hashable, TypeVar

T = TypeVar("T")


class LruCache:
    """Ответ за дату детерминирован, поэтому хранится целиком; вытесняется давно не запрошенное."""

    def __init__(self, max_entries: int) -> None:
        self._max = max_entries
        self._items: OrderedDict[Hashable, object] = OrderedDict()
        # Один замок на расчёт: одновременные запросы одной даты считают её один раз,
        # а библиотека эфемерид всё равно не допускает параллельной работы.
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get_or_compute(self, key: Hashable, compute: Callable[[], T]) -> T:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                self.hits += 1
                return self._items[key]  # type: ignore[return-value]
            value = compute()
            self.misses += 1
            self._items[key] = value
            if len(self._items) > self._max:
                self._items.popitem(last=False)
            return value

    def __len__(self) -> int:
        return len(self._items)
