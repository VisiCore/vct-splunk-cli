"""Strict parsing helpers shared by command inputs."""

from __future__ import annotations

import os
from collections.abc import Iterable

from .errors import UsageError


def parse_key_value_pairs(pairs: Iterable[str]) -> dict[str, str]:
    """Parse unique, non-empty ``KEY=VALUE`` pairs while preserving empty values."""
    parsed: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise UsageError(f"Expected KEY=VALUE (got {pair!r}).")
        key, value = pair.split("=", 1)
        if not key:
            raise UsageError("Expected a non-empty key before '='.")
        if key in parsed:
            raise UsageError(f"Duplicate key {key!r}.")
        parsed[key] = value
    return parsed


def env_flag(name: str, *, default: bool) -> bool:
    """Read a boolean env var: unset gives ``default``; ``0``/``false``/``no`` are false."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no"}
