"""Minimal, read-only Splunk Cloud ACS (Admin Config Service) support.

This is a thin client over the ACS ``adminconfig/v2`` API plus the exact read
paths the CLI uses, pinned against a vendored OpenAPI subset
(``openapi/adminconfig-v2.json``). It is **read-only** this release, and cloud
coverage is **not yet certified** against a live stack -- confidence is capped
until a real canary exists.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).parent / "openapi" / "adminconfig-v2.json"


@lru_cache(maxsize=1)
def pinned_spec() -> dict[str, Any]:
    """Return the vendored ACS OpenAPI subset our client is pinned to."""
    return json.loads(_SPEC_PATH.read_text())
