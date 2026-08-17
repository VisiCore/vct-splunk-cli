#!/usr/bin/env python3
"""Fail when Cloud CI artifacts appear to contain targets or credentials."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_ENV_NAMES = (
    "SPLUNK_URL",
    "SPLUNK_ACS_STACK",
    "SPLUNK_ACS_BASE_URL",
    "SPLUNK_ACS_TOKEN",
    "SPLUNK_TOKEN",
)
_PATTERNS = (
    re.compile(r"Bearer "),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(r"admin\.splunk\.com/(?!<redacted>(?:/|$))[^/\s]+", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9-])(?!<redacted>\.)[A-Za-z0-9-]+\.splunkcloud\.com", re.IGNORECASE),
)


def _count_matches(line: str, literals: tuple[str, ...]) -> int:
    """Count leak signatures in one line without retaining their values."""
    return sum(line.count(value) for value in literals) + sum(
        len(pattern.findall(line)) for pattern in _PATTERNS
    )


def main(argv: list[str]) -> int:
    """Scan each requested artifact and return nonzero when a leak is found."""
    literals = tuple(value for name in _ENV_NAMES if len(value := os.environ.get(name, "")) >= 4)
    found = False
    for name in argv:
        path = Path(name)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            print(f"{path}:missing", file=sys.stderr)
            continue
        for line_number, line in enumerate(lines, start=1):
            count = _count_matches(line, literals)
            if count:
                print(f"{path}:{line_number}:{count}", file=sys.stderr)
                found = True
    return int(found)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
