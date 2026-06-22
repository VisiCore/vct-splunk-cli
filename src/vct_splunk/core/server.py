"""`server info` operation. Click-free core."""

from __future__ import annotations

from typing import Any

from .client import SplunkClient


def get_server_info(client: SplunkClient) -> dict[str, Any]:
    body = client.get("/services/server/info")
    entries = body.get("entry") or []
    content = entries[0].get("content", {}) if entries else {}
    return {
        "server_name": content.get("serverName"),
        "version": content.get("version"),
        "build": content.get("build"),
        "server_roles": content.get("server_roles"),
        "os_name": content.get("os_name"),
        "guid": content.get("guid"),
    }
