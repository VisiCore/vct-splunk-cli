"""Licensing reads: installed licenses and usage. Click-free core.

System-level (not namespaced) reads over ``/services/licenser/*``. Response
shapes vary by Splunk version, so fields are pulled defensively with ``.get``.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError

_LICENSES = "/services/licenser/licenses"
_POOLS = "/services/licenser/pools"


def list_licenses(client: SplunkClient) -> list[dict[str, Any]]:
    """List installed licenses."""
    return [_license(e) for e in client.get_collection(_LICENSES)]


def get_license(client: SplunkClient, name: str) -> dict[str, Any]:
    """Show one license by its name (license hash)."""
    entries = client.get(f"{_LICENSES}/{name}").get("entry") or []
    if not entries:
        raise NotFoundError(f"License {name!r} not found.")
    return _license(entries[0])


def license_usage(client: SplunkClient) -> list[dict[str, Any]]:
    """Report per-pool license usage (quota vs. used volume)."""
    return [_pool(e) for e in client.get_collection(_POOLS)]


def _license(entry: dict[str, Any]) -> dict[str, Any]:
    c = entry.get("content") or {}
    return {
        "name": entry.get("name"),
        "label": c.get("label"),
        "type": c.get("type"),
        "quota_bytes": c.get("quota"),
        "expiration_time": c.get("expiration_time"),
        "max_violations": c.get("max_violations"),
    }


def _pool(entry: dict[str, Any]) -> dict[str, Any]:
    c = entry.get("content") or {}
    return {
        "name": entry.get("name"),
        "stack_id": c.get("stack_id"),
        "quota_bytes": c.get("quota"),
        "used_bytes": c.get("used_bytes"),
    }
