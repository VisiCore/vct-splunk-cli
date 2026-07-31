"""`server info` operation. Click-free core."""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import APIError, UsageError

_REDACTED = "<redacted>"


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


def restart_server(client: SplunkClient) -> dict[str, Any]:
    """Restart the Splunk server (a gated, blast-radius-significant write)."""
    return client.write("POST", "/services/server/control/restart", {})


def get_settings(client: SplunkClient) -> dict[str, Any]:
    """Show the server's general settings."""
    body = client.get("/services/server/settings/settings")
    entries = body.get("entry") or []
    content = entries[0].get("content") or {} if entries else {}
    return _redact_settings(content)


def set_settings(client: SplunkClient, settings: dict[str, Any]) -> dict[str, Any]:
    """Apply changed server settings (form keys); a gated write."""
    try:
        result = client.write("POST", "/services/server/settings/settings", settings)
    except APIError as exc:
        raise APIError(
            exc.message, status=exc.status, details=_redact_settings(exc.details)
        ) from exc
    if result.get("dry_run"):
        return _redact_settings(result)
    entries = result.get("entry") or []
    content = entries[0].get("content") or {} if entries else result
    return _redact_settings(content)


def _redact_settings(value: Any) -> Any:
    """Recursively replace secret-bearing server-setting values."""
    if isinstance(value, dict):
        return {
            key: _REDACTED if _secret_setting(key) else _redact_settings(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_settings(item) for item in value]
    return value


def _secret_setting(key: object) -> bool:
    normalized = str(key).casefold().replace("_", "").replace("-", "")
    return any(
        marker in normalized for marker in ("pass4symmkey", "password", "passwd", "secret", "token")
    )
