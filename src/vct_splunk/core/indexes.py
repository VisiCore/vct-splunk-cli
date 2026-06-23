"""Index operations: list / get / create / update / delete / enable / disable.
Click-free core."""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError

_PATH = "/services/data/indexes"


def list_indexes(client: SplunkClient) -> list[dict[str, Any]]:
    return [_index(e) for e in client.get_collection(_PATH)]


def get_index(client: SplunkClient, name: str) -> dict[str, Any]:
    entries = (client.get(f"{_PATH}/{name}").get("entry")) or []
    if not entries:
        raise NotFoundError(f"Index {name!r} not found.")
    return _index(entries[0])


def create_index(
    client: SplunkClient, name: str, *, max_gb: float | None = None, frozen_secs: int | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {"name": name, **_settings(max_gb, frozen_secs)}
    return _unwrap(client.write("POST", _PATH, data))


def update_index(
    client: SplunkClient, name: str, *, max_gb: float | None = None, frozen_secs: int | None = None
) -> dict[str, Any]:
    """Update an existing index's settings.

    A POST to the named index merges server-side, so only the settings that
    changed are sent -- there is no read-modify-write. (Splunk's POST merges; it
    does not replace, so we do not need to fetch-then-overlay the way a PUT-style
    API would.)
    """
    return _unwrap(client.write("POST", f"{_PATH}/{name}", _settings(max_gb, frozen_secs)))


def delete_index(client: SplunkClient, name: str) -> dict[str, Any]:
    return client.write("DELETE", f"{_PATH}/{name}", {})


def enable_index(client: SplunkClient, name: str) -> dict[str, Any]:
    return _unwrap(client.write("POST", f"{_PATH}/{name}/enable", {}))


def disable_index(client: SplunkClient, name: str) -> dict[str, Any]:
    return _unwrap(client.write("POST", f"{_PATH}/{name}/disable", {}))


def _settings(max_gb: float | None, frozen_secs: int | None) -> dict[str, Any]:
    """Map the CLI's friendly options to Splunk's index settings (form keys)."""
    data: dict[str, Any] = {}
    if max_gb is not None:
        data["maxTotalDataSizeMB"] = int(max_gb * 1024)
    if frozen_secs is not None:
        data["frozenTimePeriodInSecs"] = int(frozen_secs)
    return data


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Return a dry-run preview unchanged, else normalize the affected index."""
    if result.get("dry_run"):
        return result
    entries = result.get("entry") or []
    return _index(entries[0]) if entries else result


def _index(entry: dict[str, Any]) -> dict[str, Any]:
    c = entry.get("content") or {}
    return {
        "name": entry.get("name"),
        "total_event_count": c.get("totalEventCount"),
        "current_size_mb": c.get("currentDBSizeMB"),
        "max_size_mb": c.get("maxTotalDataSizeMB"),
        "frozen_time_period_secs": c.get("frozenTimePeriodInSecs"),
        "disabled": c.get("disabled"),
    }
