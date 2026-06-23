"""`server info` operation. Click-free core."""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import UsageError


def get_server_info(client: SplunkClient) -> dict[str, Any]:
    body = client.get("/services/server/info")
    entries = body.get("entry") or []
    if not entries:
        # A non-REST endpoint (e.g. the web UI on :443/:8000) can answer 200 with
        # HTML, which decodes to {"raw": ...} and carries no "entry". Returning
        # all-null fields would hide that mistake; fail clearly and name the cause.
        raise UsageError(
            "Splunk did not return REST JSON from /services/server/info. "
            "Is SPLUNK_URL the management port (:8089), not the web UI?"
        )
    content = entries[0].get("content", {})
    return {
        "server_name": content.get("serverName"),
        "version": content.get("version"),
        "build": content.get("build"),
        "server_roles": content.get("server_roles"),
        "os_name": content.get("os_name"),
        "guid": content.get("guid"),
    }
