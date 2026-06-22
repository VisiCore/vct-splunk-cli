"""Index operations: list / get / create (+ delete, used by tests). Click-free core."""

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
    data: dict[str, Any] = {"name": name}
    if max_gb is not None:
        data["maxTotalDataSizeMB"] = int(max_gb * 1024)
    if frozen_secs is not None:
        data["frozenTimePeriodInSecs"] = int(frozen_secs)
    result = client.write("POST", _PATH, data)
    if isinstance(result, dict) and result.get("dry_run"):
        return result
    entries = result.get("entry") or []
    return _index(entries[0]) if entries else result


def delete_index(client: SplunkClient, name: str) -> dict[str, Any]:
    """Not a CLI command in the MVP; used by integration tests for cleanup."""
    return client.write("DELETE", f"{_PATH}/{name}", {})


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
