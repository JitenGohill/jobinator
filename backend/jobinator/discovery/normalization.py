from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def required_string(
    payload: Mapping[str, Any],
    key: str,
    error_factory: Callable[[], Exception],
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise error_factory()
    return value.strip()
