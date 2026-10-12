"""Загрузка файла с проверкой контрольной суммы. Используется только скриптами tools/."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, target: Path, expected_sha256: str) -> bool:
    """Скачивает файл, если его нет или он не тот. False — контрольная сумма не совпала."""
    if target.exists() and sha256(target) == expected_sha256:
        print(f"уже на месте: {target}")
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    print(f"загрузка {url}")
    urllib.request.urlretrieve(url, partial)
    actual = sha256(partial)
    if actual != expected_sha256:
        partial.unlink()
        print(f"контрольная сумма не совпала: {target.name}: {actual}")
        return False
    partial.replace(target)
    print(f"готово: {target}")
    return True
