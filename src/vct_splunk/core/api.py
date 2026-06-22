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
    """GET an arbitrary Splunk REST endpoint and return the decoded JSON body.

    This is the raw read-only escape hatch behind ``splunk api get``. To keep it
    read-only and aimed at the REST API, *path* must live under one of Splunk's
    REST roots:

    * ``/services/...`` — the standard, app-agnostic endpoints.
    * ``/servicesNS/<user>/<app>/...`` — the namespaced variants, scoped to a
      particular user and app context (many read endpoints are only reachable
      this way).

    Args:
        client: An open Splunk client.
        path: The REST path to GET, with or without a leading slash.
        query: Optional query-string parameters.

    Returns:
        The parsed JSON response body.

    Raises:
        UsageError: If *path* is not under ``/services/`` or ``/servicesNS/``.
    """
    if not path.lstrip("/").startswith(("services/", "servicesNS/")):
        raise UsageError(f"Path must be under /services/ or /servicesNS/ (got {path!r}).")
    return client.get(path, params=query)
