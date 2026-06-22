"""GET-only raw REST escape hatch. Click-free core.

Exposes the whole Splunk read API to callers without a typed command per endpoint.
Writes are intentionally *not* reachable here — they go through gated commands only.
The raw body includes Splunk's ``paging`` block, so callers can see ``total`` vs.
returned and know whether more exists.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import UsageError


def api_get(client: SplunkClient, path: str, query: dict[str, str] | None = None) -> Any:
    if not path.lstrip("/").startswith("services/"):
        raise UsageError(f"Path must be under /services/ (got {path!r}).")
    return client.get(path, params=query)
